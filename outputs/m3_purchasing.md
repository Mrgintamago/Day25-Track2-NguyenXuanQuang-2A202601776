# M3-01 — Chiến lược mua GPU

> Ticket `M3-01` trong [`PLAN.md`](../PLAN.md) · Chạy: `python missions/m3_purchasing.py`
> Module: `finops/pricing.py` · Slide §4

---

## DoD — trạng thái

- [x] Có job `spot` (5 job) và job `reserved` (3 job)
- [x] Tổng chi phí giảm: **$25,667 → $15,627/tháng (−39.1%)**
- [x] Giải thích được `effective_hours > job_hours`
- [x] `verify.py` → 3 check M3 đều PASS

---

## 1. Output của mission

```
== M3 Purchasing Strategy ==
break-even utilization @ 45% reserved discount = 55%
job               gpu    tier          on-demand   optimized
job-train-llm     H100   spot          $12,000      $7,596
job-train-embed   A100   spot           $2,148      $1,393
job-finetune      H100   spot             $900        $570
job-infer-chat    A10G   reserved       $4,320      $2,592
job-infer-rag     A100   reserved       $3,866      $2,160
job-infer-search  L4     reserved       $1,728        $972
job-dev-sandbox   A10G   spot             $480        $203
job-batch-eval    H100   spot             $225        $142

monthly: on-demand $25,667 -> optimized $15,627  (39.1% saved)
```

---

## 2. Trả lời 3 câu hỏi phân tích (Guide §6.4)

### Câu 1 — Job nào được đề xuất spot? Tại sao?

**5/8 job:** `job-train-llm`, `job-train-embed`, `job-finetune`, `job-dev-sandbox`, `job-batch-eval`.

Điều kiện duy nhất trong policy hiện tại là `interruptible=1`:

```python
if interruptible and hours_per_day < 24:
    return "spot"
```

Đúng 5 job đó có `interruptible=1`, và không có job nào chạy 24/24. Chú ý **duty cycle không hề được xét** ở nhánh này — `job-train-llm` (83%) và `job-batch-eval` (12.5%) đều bị đẩy sang spot như nhau.

**Vì sao interruptible là điều kiện đúng:** spot nghĩa là nhà cung cấp có quyền lấy lại máy bất cứ lúc nào. Job chịu được điều đó phải có hai tính chất: **checkpoint được** (mất tiến độ có giới hạn) và **không có người ngồi chờ** (không SLA latency). Cả 3 job `train` + sandbox + batch-eval đều thỏa. Ngược lại, 3 job `infer` phục vụ người dùng — bị giết giữa chừng là mất request, không phải mất tiến độ.

### Câu 2 — `effective_hours > job_hours` nghĩa là gì?

Với `job-train-llm` (2,240 GPU-giờ H100):

```python
spot_checkpoint_cost(2240, spot_hr=1.5, on_demand_hr=2.5)
# {'spot_effective_hours': 2363.2, 'spot_cost': 3544.8,
#  'on_demand_cost': 5600.0, 'savings_pct': 36.7}
```

**2,363.2 giờ phải trả tiền cho 2,240 giờ công việc thật — dôi ra 123.2 giờ (+5.5%).** Phần dôi đến từ hai nguồn:

| Nguồn | Công thức | Giờ |
|---|---|---|
| Overhead ghi checkpoint | `2240 × 3%` | 67.2 |
| Chạy lại sau khi bị thu hồi | `2240 × 5%/h × 0.5h` | 56.0 |
| **Tổng dôi ra** | | **123.2** |

Ý nghĩa: **spot không phải "GPU giá $1.50" — spot là "GPU giá $1.50 và bạn phải mua nhiều giờ hơn."** Giá hiệu dụng thật:

```
$3,544.80 ÷ 2,240 giờ thật = $1.58/giờ   (không phải $1.50)
```

Đây là lý do so sánh spot bằng cách nhìn bảng giá là sai. Con số đúng để so là **giá hiệu dụng sau khi cộng rework + overhead**.

**Vì sao vẫn nên chọn spot:** $1.58 vẫn thấp hơn nhiều so với on-demand $2.50 → tiết kiệm 36.7%. Nhưng lưu ý con số **36.7% này thấp hơn mức chiết khấu danh nghĩa 40%** ghi trên bảng giá. Chênh lệch 3.3 điểm đó chính là **cái giá của việc bị đuổi**.

### Câu 3 — Có job nào bạn nghĩ policy chọn sai không?

**Có — và đây là phần thú vị nhất của M3.** So sánh đầy đủ cả 4 phương án cho từng job ($/tháng):

| job | duty% | int | policy chọn | on-demand | spot | rsv 3yr | rsv 1yr | rẻ nhất về số học |
|---|---|---|---|---|---|---|---|---|
| job-train-llm | 83.3 | 1 | **spot** $7,596 | 12,000 | 7,596 | **6,720** | 9,600 | rsv3y |
| job-train-embed | 41.7 | 1 | **spot** $1,393 | 2,148 | 1,393 | **1,200** | 1,680 | rsv3y |
| job-finetune | 25.0 | 1 | **spot** $570 | 900 | 570 | **504** | 720 | rsv3y |
| job-infer-chat | 100.0 | 0 | **reserved** $2,592 | 4,320 | *(1,823)* | **2,592** | 3,456 | rsv3y |
| job-infer-rag | 100.0 | 0 | **reserved** $2,160 | 3,866 | *(2,507)* | **2,160** | 3,024 | rsv3y |
| job-infer-search | 75.0 | 0 | **reserved** $972 | 1,728 | *(798)* | **972** | 1,296 | rsv3y |
| job-dev-sandbox | 33.3 | 1 | **spot** $203 | 480 | **203** | 288 | 384 | spot |
| job-batch-eval | 12.5 | 1 | **spot** $142 | 225 | 142 | **126** | 180 | rsv3y |

*(cột spot in nghiêng = không dùng được vì `interruptible=0`)*

| | $/tháng | vs on-demand |
|---|---|---|
| on-demand toàn bộ | 25,667 | — |
| **policy hiện tại** | **15,627** | **−39.1%** |
| "rẻ nhất về số học" | 14,477 | −43.6% |
| **Chênh lệch** | **$1,151/tháng** | |

**Nhưng $1,151 đó KHÔNG phải tiền bị bỏ lỡ — đó là cái bẫy.**

Số học nói `job-train-llm` nên dùng reserved 3 năm ($6,720 < $7,596). Nhưng nhìn cột `days` trong `workloads.csv`:

| job | `days` | Cam kết reserved |
|---|---|---|
| job-train-llm | **14** | 1,095 ngày |
| job-train-embed | **5** | 1,095 ngày |
| job-finetune | **3** | 1,095 ngày |
| job-batch-eval | 30 | 1,095 ngày |

Ký hợp đồng **3 năm** cho một job training chạy **14 ngày** nghĩa là trả cho 1,081 ngày không dùng. Phép so sánh theo `$/giờ` không thấy điều đó vì nó ngầm giả định bạn sẽ dùng hết thời hạn cam kết.

> **Bài học:** *thời hạn cam kết không được dài hơn độ chắc chắn của bạn về nhu cầu.* Reserved rẻ hơn **mỗi giờ**, nhưng bạn trả **mọi giờ** trong hợp đồng — dùng hay không.

Vậy policy có sai chỗ nào thật không? **Có hai chỗ:**

1. **`job-dev-sandbox` → spot là lựa chọn đúng thật** ($203, rẻ nhất mọi phương án). Policy đúng ở đây một cách tình cờ.
2. **3 job `infer` có spot rẻ hơn reserved** (`job-infer-search`: $798 vs $972) nhưng không dùng được vì `interruptible=0`. Đây là điểm cần thảo luận: các job này *thật sự* không gián đoạn được, hay chỉ chưa ai đầu tư làm graceful drain + multi-region failover? Nếu chuyển được `job-infer-search` sang spot thì tiết kiệm thêm $174/tháng — nhưng đổi lấy rủi ro SLA.

**Điểm yếu thật của M3 (input cho `EXT-01`):**

- **Bỏ qua cột `days` hoàn toàn.** Code dùng `DAYS = 30` cho cả 8 job, kể cả job chỉ chạy 3 ngày. Chi phí `job-finetune` bị thổi lên **10×**.
- **Hardcode `reserved_discount=0.45`** trong khi chiết khấu thật khác nhau theo GPU (xem mục 3).
- **Chỉ so reserved 3yr**, không bao giờ xét reserved 1yr.
- **Nhánh spot đặt trước nhánh duty cycle** → job interruptible không bao giờ được cân nhắc reserved dù duty 83%.

---

## 3. Điểm hòa vốn — con số quan trọng nhất của M3

```python
break_even_utilization(0.45) = 1 - 0.45 = 0.55   # 55% = 13.2 giờ/ngày
```

**Trực giác:** reserved rẻ hơn 45% **mỗi giờ**, nhưng bạn trả **cả 24 giờ** dù dùng hay không. Chạy dưới 13.2 giờ/ngày thì phần trả cho giờ nằm không đã ăn hết khoản chiết khấu.

Nhưng code hardcode 45%. Chiết khấu **thật** trong `price_catalog.csv` khác nhau theo từng GPU:

| GPU | rsv 3yr −% | Break-even | Giờ/ngày | rsv 1yr −% | Break-even 1yr |
|---|---|---|---|---|---|
| H100 | 44.0% | 56.0% | 13.4h | 20.0% | 19.2h |
| H200 | 39.2% | 60.8% | 14.6h | 19.0% | 19.4h |
| A100 | 44.1% | 55.9% | 13.4h | 21.8% | 18.8h |
| A10G | 40.0% | 60.0% | 14.4h | 20.0% | 19.2h |
| L4 | 43.8% | 56.2% | 13.5h | 25.0% | 18.0h |
| B200 | 37.1% | **62.9%** | **15.1h** | 17.5% | 19.8h |
| MI300X | 38.5% | 61.5% | 14.8h | 17.9% | 19.7h |

Hai quan sát:

- **Break-even thật dao động 55.9% → 62.9%**, không phải 55% cho tất cả. Với B200 bạn cần **15.1 giờ/ngày**, không phải 13.2. Dùng nhầm ngưỡng cho GPU mới nhất là cách dễ nhất để mua hớ.
- **Reserved 1 năm cần duty 18–19.8 giờ/ngày** — gần như phải chạy 24/7 mới hòa vốn. Cam kết ngắn hơn thì chiết khấu mỏng hơn nhiều (17–25% so với 37–44%), nên ngưỡng dựng đứng lên. Đây là đánh đổi thật: **linh hoạt có giá của nó.**

---

## 4. Mô phỏng spot: chịu được bao nhiêu lần bị đuổi?

Thử `job-train-llm` (2,240 GPU-giờ H100) với các mức `interrupt_rate` khác nhau:

| interrupt_rate/giờ | effective hours | Chi phí spot | Tiết kiệm |
|---|---|---|---|
| 2% | 2,329.6 | $3,494 | 37.6% |
| **5%** *(mặc định)* | **2,363.2** | **$3,545** | **36.7%** |
| 10% | 2,419.2 | $3,629 | 35.2% |
| 20% | 2,531.2 | $3,797 | 32.2% |
| 40% | 2,755.2 | $4,133 | 26.2% |

Ngay cả ở mức bị thu hồi **40%/giờ**, spot vẫn tiết kiệm 26%. Mô hình cho thấy spot chỉ hết lợi khi `interrupt_rate > 127%/giờ` — tức là **không bao giờ**.

**Nhưng đây là điểm yếu của mô hình, không phải sự thật về spot.** Lý do: `rework_hours_per_interrupt = 0.5` là **hằng số**. Mô hình giả định mỗi lần bị đuổi chỉ mất 30 phút, bất kể checkpoint cách nhau bao lâu và bất kể phải chờ bao lâu mới xin lại được máy.

Thực tế thiếu ba thứ:

1. **Mất tiến độ tỷ lệ với khoảng cách checkpoint.** Checkpoint 6 giờ/lần thì trung bình mất 3 giờ, không phải 0.5.
2. **Thời gian chờ có máy lại.** Khi thị trường spot cạn, job có thể nằm chờ hàng giờ — deadline trượt, dù hóa đơn không tăng.
3. **Chi phí lưu trữ checkpoint.** Ghi checkpoint model lớn tốn I/O và dung lượng object storage.

> Bài học chung: mô hình luôn cho câu trả lời; việc của bạn là biết **giả định nào đang đỡ câu trả lời đó**. Ở đây, "spot luôn thắng" đứng được hoàn toàn nhờ giả định rework cố định 0.5 giờ.

---

## 5. Kiểm chứng

```bash
$ python verify.py | grep M3
  [PASS] M3 recommends a spot tier  ({'spot', 'reserved'})
  [PASS] M3 recommends a reserved tier  ({'spot', 'reserved'})
  [PASS] M3 purchasing saves money  (39.1%)
```

---

## Kết nối sang ticket tiếp theo

| Phát hiện M3 | Dùng ở đâu |
|---|---|
| Purchasing: $25,667 → $15,627/tháng (−39.1%) | `M5-01` lever "Purchasing" |
| M3 bỏ qua cột `days`; hardcode discount 45%; không xét rsv 1yr | `EXT-01` — viết lại `recommend_tier()` |
| Break-even thật 55.9–62.9% tùy GPU | `EXT-01` — tính discount theo từng GPU |
| `rework_hours_per_interrupt` cố định 0.5h làm spot luôn thắng | `EXT-01` — mô hình interruption thực tế hơn |
| 5/8 job interruptible → cũng đổi vùng được | `EXT-05` — carbon-aware scheduling |
| Giá spot hiệu dụng $1.58/h (không phải $1.50) | `DOC-01` — khuyến nghị |
