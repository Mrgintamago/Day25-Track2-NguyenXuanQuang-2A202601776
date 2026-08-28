# EXT-01 + EXT-02 — Hai phần mở rộng "Your Turn"

> Ticket `EXT-01` và `EXT-02` trong [`PLAN.md`](../PLAN.md)
> Code: `finops/pricing.py`, `missions/m1_efficiency_audit.py`, `missions/m3_purchasing.py`
> Test mới: `tests/test_ext_policies.py` (12 test)
> Trạng thái: **`pytest` 27/27 passed** · **`verify.py` 11/11 passed** *(không phá vỡ gì)*

---

# EXT-01 — Viết lại `recommend_tier()`

## 1. Ba lỗi trong policy gốc

Policy gốc chỉ nhìn 2 biến (`hours_per_day`, `interruptible`) và hardcode discount 45%. Ba lỗi cụ thể tìm được ở `M3-01`:

| # | Lỗi | Hậu quả đo được |
|---|---|---|
| 1 | **Bỏ qua cột `days`** — `DAYS = 30` cho cả 8 job | Baseline on-demand bị thổi từ **$16,539 → $25,667** (+55%). `job-finetune` chạy 3 ngày bị tính như 30 ngày |
| 2 | **Hardcode `reserved_discount=0.45`** | Break-even thật là 55.9–62.9% tùy GPU, không phải 55% cho tất cả |
| 3 | **Reserved chỉ tính giờ job chạy** — `gpu_hours × reserved_3yr_hr` | Reservation bill **24h/ngày** dù dùng hay không. Với `job-infer-search` (duty 75%) v1 tính $972 trong khi thật là $1,296 — **thiếu 25%** |

Thêm hai thiếu sót: không bao giờ xét reserved 1yr, và `spot_checkpoint_cost` dùng chung `interrupt_rate=0.05` cho mọi loại GPU.

## 2. Policy mới

Thêm vào `finops/pricing.py` — `recommend_tier()` giữ nguyên hành vi cũ khi không truyền `price_row` (5 test cũ vẫn pass), và bật logic mới khi có:

```python
SPOT_INTERRUPT_RATE = {"H100": 0.03, "H200": 0.04, "B200": 0.06,
                       "MI300X": 0.06, "A100": 0.05, "A10G": 0.12, "L4": 0.15}
RESERVED_TERM_DAYS = {"reserved_1yr_hr": 365, "reserved_3yr_hr": 1095}
DEMAND_VISIBILITY_DAYS = 365   # bạn chỉ được cam kết xa bằng tầm nhìn của mình
```

**Interrupt rate lấy từ chính bảng giá:** thị trường đã định giá rủi ro thu hồi vào mức chiết khấu spot. A10G có spot rẻ nhất tương đối (−60%) và L4 (−56%) — cũng chính là hai GPU bị thu hồi nhiều nhất. Không phải con số bịa; nó đọc được từ `price_catalog.csv`.

**Bốn cải tiến:**

1. **Spot được *định giá*, không phải mặc định.** Job interruptible trên A10G (12%/giờ) có thể thua reserved dù vẫn interruptible.
2. **Cam kết chỉ hợp lệ với công việc thực sự lặp lại**, và chỉ xa bằng tầm nhìn nhu cầu:
   ```python
   commitment_utilization(hours_per_day, demand_days, term_days)
       = duty × min(1, demand_days / term_days)
   ```
   Job 14 ngày dùng **~1%** của term 3 năm → mọi cam kết bị loại.
3. **Break-even đọc từ catalog** theo từng GPU và từng term, không hardcode.
4. **1yr và 3yr cạnh tranh nhau**; hòa giá thì **ưu tiên phương án ít ràng buộc hơn** (on_demand > spot > 1yr > 3yr).

Chạy: `python -c "from missions import m3_purchasing as m3; m3.run(policy='v2')"`

## 3. Đo lường trước/sau

**So sánh công bằng** — cả hai chạy trên cùng horizon days-aware (v1 gốc bill 30 ngày cho mọi job nên không so trực tiếp được):

| job | GPU | days | v1 tier | **v2 tier** | on-demand | v1 $ | **v2 $** | Δ |
|---|---|---|---|---|---|---|---|---|
| job-train-llm | H100 | 14 | spot | **spot** | 5,600 | 3,545 | **3,511** | +34 |
| job-train-embed | A100 | 5 | spot | **spot** | 358 | 232 | **232** | 0 |
| job-finetune | H100 | 3 | spot | **spot** | 90 | 57 | **56** | +1 |
| job-infer-chat | A10G | 30 | reserved *(3yr)* | **reserved_1yr** | 4,320 | 2,592 | **3,456** | −864 |
| job-infer-rag | A100 | 30 | reserved *(3yr)* | **reserved_1yr** | 3,866 | 2,160 | **3,024** | −864 |
| job-infer-search | L4 | 30 | reserved *(3yr)* | **on_demand** | 1,728 | 972 | **1,728** | −756 |
| job-dev-sandbox | A10G | 22 | spot | **spot** | 352 | 149 | **153** | −5 |
| job-batch-eval | H100 | 30 | spot | **spot** | 225 | 142 | **141** | +1 |

| | Tổng $/tháng | Tiết kiệm |
|---|---|---|
| on-demand (days-aware) | 16,539 | — |
| **v1 policy** | **9,849** | **40.5%** |
| **v2 policy (EXT-01)** | **12,302** | **25.6%** |

### **v2 đắt hơn v1 $2,453/tháng — và đó là kết quả đúng**

Đây là phát hiện quan trọng nhất của EXT-01, nên nói thẳng thay vì giấu.

Khoản "tiết kiệm" 40.5% của v1 **một phần là hư cấu**, vì nó dựa trên hai giả định không ai kiểm chứng:

- **Ký reserved 3 năm cho workload mới có 30 ngày bằng chứng.** Nếu sản phẩm đổi hướng sau 8 tháng, bạn còn 28 tháng hợp đồng phải trả.
- **Chỉ trả tiền cho giờ job chạy.** Sai — reservation bill 24/7. Sửa riêng lỗi này, v1 thật ra tốn $10,173 chứ không phải $9,849.

v2 nói: *với 365 ngày tầm nhìn, bạn chỉ được ký 1 năm.* Reserved 1yr chiết khấu mỏng hơn nhiều (17–25% so với 37–44%) nên hóa đơn cao hơn — nhưng khoản đó **thực sự hiện thực hóa được**.

> **Bài học:** một policy tối ưu hóa có thể "cải thiện" con số bằng cách âm thầm nhận thêm rủi ro. Câu hỏi đúng không phải *"policy nào cho số đẹp hơn"* mà *"số đó dựa trên giả định nào, và ta có tin nổi giả định đó không"*.

### Độ nhạy theo tầm nhìn nhu cầu

Chính sách phản ứng đúng khi ta tự tin hơn:

| Tầm nhìn (ngày) | Tổng $/tháng | vs on-demand | Tier được chọn |
|---|---|---|---|
| 30 | 14,009 | 15.3% | 5 spot · 3 on-demand |
| 90 | 14,009 | 15.3% | 5 spot · 3 on-demand |
| 180 | 14,009 | 15.3% | 5 spot · 3 on-demand |
| **365** *(mặc định)* | **12,302** | **25.6%** | 5 spot · 2 rsv-1yr · 1 on-demand |
| 730 | 10,574 | 36.1% | 5 spot · 2 **rsv-3yr** · 1 on-demand |
| 1095 | **10,142** | **38.7%** | 5 spot · 3 **rsv-3yr** |

Đường cong này chính là **giá trị bằng tiền của sự chắc chắn**: đi từ 6 tháng lên 3 năm tầm nhìn đáng giá **$3,867/tháng**. Đó là lý do FinOps engineer nên ngồi họp roadmap sản phẩm — thông tin đó có giá cụ thể.

Ở mức 1095 ngày, v2 chọn đúng như v1 nhưng tính tiền đúng hơn ($10,142 vs $10,173 sau khi sửa lỗi bill 24/7 của v1).

## 4. Ma trận đề xuất

Policy v2 rút gọn thành ma trận (tầm nhìn 365 ngày):

| | `days` < 30 (một lần) | `days` ≥ 30 (lặp lại), duty < break-even | `days` ≥ 30, duty ≥ break-even |
|---|---|---|---|
| **interruptible = 1** | **spot** *(rate theo GPU)* | **spot** | spot vs reserved — so giá |
| **interruptible = 0** | **on_demand** | **on_demand** | **reserved_1yr** *(3yr nếu tầm nhìn ≥ 730d)* |

Break-even lấy từ catalog theo GPU: 3yr **55.9–62.9%** · 1yr **72–82.5%**.

---

# EXT-02 — Right-sizing theo MBU

## 1. `$/GPU-hr` giấu điều gì

Thêm `unit_prices()` vào `missions/m1_efficiency_audit.py`:

| GPU | $/hr | VRAM | BW TB/s | **$/GB-hr** | **$/TB/s-hr** | $/TFLOP-hr |
|---|---|---|---|---|---|---|
| **MI300X** | 1.95 | 192 | 5.30 | **0.0102** | **0.368** | **1.492** |
| A100 | 1.79 | 80 | 2.00 | 0.0224 | 0.895 | 5.737 |
| B200 | 5.09 | 192 | 8.00 | 0.0265 | 0.636 | 2.262 |
| H200 | 3.95 | 141 | 4.80 | 0.0280 | 0.823 | 3.990 |
| H100 | 2.50 | 80 | 3.35 | 0.0312 | 0.746 | 2.525 |
| L4 | **0.80** | 24 | 0.30 | 0.0333 | 2.667 | 6.612 |
| A10G | 1.00 | 24 | 0.60 | 0.0417 | 1.667 | 8.000 |

### Trả lời câu hỏi chấm điểm: *"Tại sao không chỉ chọn GPU rẻ nhất theo `$/GPU-hr`?"*

**Hai bảng xếp hạng đảo ngược nhau:**

- Rẻ nhất theo `$/GPU-hr`: **L4** ($0.80)
- Rẻ nhất theo `$/GB-VRAM-hr`: **MI300X** ($0.0102) — **rẻ hơn L4 3.3×**
- L4 xếp **áp chót** về $/GB và **chót** về $/(TB/s) — đắt hơn MI300X **7.2×** trên mỗi đơn vị băng thông

L4 là cái hộp rẻ nhất, nhưng là **cách đắt nhất để mua băng thông**. Với workload decode (memory-bound, arithmetic intensity ~1–2 FLOP/byte), băng thông mới là thứ sinh ra token. Mua L4 vì nó rẻ theo giờ là trả nhiều tiền hơn cho mỗi token.

Ngược lại **B200 $5.09/h — đắt nhất bảng — lại rẻ thứ 3 theo $/GB và thứ 2 theo $/(TB/s)**. Giá theo giờ nói lên rất ít.

## 2. Đề xuất right-sizing

`rightsize_by_mbu()` chọn GPU thay thế dựa trên **những gì thiết bị thực sự tiêu thụ**, không phải nhãn nó đang mang:

- Ràng buộc: `peak_bw ≥ max(achieved_bw) × 1.25`, `peak_tflops ≥ max(achieved) × 1.25`, `hbm_gb ≥ max(mem_used) × 1.25`
- **Chỉ đụng vào GPU thực sự thừa công suất** — MFU < 0.35 **và** MBU < 0.60. GPU khỏe mạnh được để yên dù phương án khác rẻ đến đâu
- Chỉ đổi nếu rẻ hơn thật

| GPU | regime | MFU | MBU | hiện tại | → đề xuất | $/tháng nay | mới | tiết kiệm | kết luận |
|---|---|---|---|---|---|---|---|---|---|
| gpu-h100-4 | balanced | 0.194 | 0.207 | H100 | **MI300X** | 1,800 | 1,404 | **396** | right-size |
| gpu-h100-5 | balanced | 0.261 | 0.271 | H100 | **MI300X** | 1,800 | 1,404 | **396** | right-size |
| gpu-h100-0..3 | balanced | 0.40–0.43 | 0.42–0.45 | H100 | H100 | 1,800 | 1,800 | 0 | keep (healthy) |
| gpu-a100-0/1 | balanced | 0.24–0.26 | 0.25–0.28 | A100 | A100 | 1,289 | 1,289 | 0 | keep (no cheaper fit) |
| gpu-a10g-0 | balanced | 0.218 | 0.235 | A10G | A10G | 720 | 720 | 0 | keep (no cheaper fit) |
| gpu-a10g-1 | **memory-bound** | 0.268 | 0.302 | A10G | A10G | 720 | 720 | 0 | keep (no cheaper fit) |
| gpu-l4-0 | balanced | 0.302 | 0.328 | L4 | L4 | 576 | 576 | 0 | keep (no cheaper fit) |

**Tổng: $792/tháng.**

So với lever "Right-size util-lies" của `M5-01` ($655/tháng): M5 dùng bảng hạ cấp cứng `H100 → A100`, đúng hướng nhưng bỏ sót hai điều — nó **không kiểm tra GPU thay thế có đủ VRAM/băng thông không**, và nó bỏ qua `gpu-h100-5` (MFU 0.261, không bị gắn cờ "lie" vì util chỉ 61%). Cách tiếp cận theo dữ liệu tiêu thụ tìm được **nhiều hơn $137/tháng** và có cơ sở kỹ thuật để bảo vệ đề xuất.

## 3. Phát hiện ngoài dự kiến: **VRAM mới là trần thật của fleet**

Khi kiểm tra ràng buộc headroom, cả 11/11 GPU đều trượt — không phải vì băng thông, mà vì **bộ nhớ**:

| GPU | Peak VRAM dùng | Dung lượng | Còn dư |
|---|---|---|---|
| gpu-h100-0/1/3 | 67.5 GB | 80 GB | **18.5%** |
| gpu-a100-0 | 67.7 GB | 80 GB | **18.2%** |
| gpu-a10g-1 | 20.4 GB | 24 GB | **17.6%** |
| gpu-l4-0 | 20.2 GB | 24 GB | 18.8% |
| *(toàn bộ 11 GPU)* | | | **17.6–20.7%** |

Toàn fleet chạy ở mức **~80–82% VRAM**, trong khi MFU chỉ 0.19–0.43 và MBU 0.21–0.45. Nghĩa là:

> **Fleet đang cạn bộ nhớ trước khi cạn sức tính toán.** Không GPU nào dùng quá 45% băng thông hay 43% FLOPs, nhưng mọi GPU đều chỉ còn dưới 21% VRAM dự phòng.

Điều này giải thích vì sao 5/11 GPU không tìm được phương án rẻ hơn: **không phải vì đắt, mà vì không GPU rẻ hơn nào đủ VRAM.** Đây chính là bài học EXT-02 ở dạng thuần khiết nhất — quyết định mua GPU trong lab này bị chi phối bởi **dung lượng bộ nhớ**, không phải TFLOPs, và cũng không phải `$/GPU-hr`.

Hệ quả thực tế: hướng tối ưu đúng cho NimbusAI không phải "mua GPU rẻ hơn" mà là **giảm nhu cầu VRAM** (quantization, KV-cache paging, tensor parallel) — làm được thì cả 11 GPU mới mở ra lựa chọn rẻ hơn.

---

## 4. Kiểm chứng

```bash
$ pytest -q
...........................             [100%]
27 passed in 1.64s          # 15 test gốc + 12 test mới, không sửa file test cũ

$ python verify.py
  11/11 checks passed       # policy mặc định vẫn là v1 nên đường graded không đổi
```

**12 test mới trong `tests/test_ext_policies.py`:**

| Test | Bảo vệ điều gì |
|---|---|
| `test_legacy_policy_is_unchanged` | Không phá vỡ hành vi cũ |
| `test_reserved_discount_read_from_catalog_not_hardcoded` | B200 break-even > 62%, không phải 55% |
| `test_interrupt_rate_varies_by_gpu_type` | A10G rủi ro hơn H100 |
| `test_short_campaign_cannot_carry_a_long_commitment` | Job 14 ngày không được ký 3 năm |
| `test_steady_workload_prefers_the_term_it_can_actually_see` | 365 ngày tầm nhìn → 1yr, không phải 3yr |
| `test_ties_go_to_the_least_binding_option` | Hòa giá thì chọn linh hoạt |
| `test_v2_policy_runs_and_still_saves_money` | M3 chạy được với policy mới |
| `test_unit_prices_rank_differently_than_dollars_per_hour` | Hai bảng xếp hạng đảo nhau |
| `test_rightsizing_leaves_healthy_gpus_alone` | Không đụng GPU MFU ≥ 0.35 |
| `test_rightsizing_targets_the_util_lie_gpu` | Bắt đúng `gpu-h100-4` |
| `test_proposed_replacement_clears_observed_bandwidth_and_memory` | Đề xuất phải đủ tài nguyên |
| `test_vram_headroom_is_reported` | VRAM headroom được đo |

---

## Tóm tắt cho `DOC-01`

| | Kết quả | Insight |
|---|---|---|
| **EXT-01** | v1 40.5% → v2 25.6% | Policy cũ "tiết kiệm" nhiều hơn **vì âm thầm nhận rủi ro cam kết 3 năm**. Tầm nhìn nhu cầu từ 6 tháng → 3 năm đáng giá **$3,867/tháng** |
| | 3 lỗi đã sửa | Bỏ qua `days` (baseline +55%), hardcode 45% (break-even thật 55.9–62.9%), reserved chỉ bill giờ chạy (thiếu 25%) |
| **EXT-02** | $792/tháng *(vs $655 của M5)* | L4 rẻ nhất theo giờ nhưng **đắt nhất 7.2× theo băng thông**; MI300X ngược lại |
| | VRAM headroom 17.6–20.7% | **Fleet cạn bộ nhớ trước khi cạn tính toán** — right-sizing bị chặn bởi VRAM, không phải giá |
