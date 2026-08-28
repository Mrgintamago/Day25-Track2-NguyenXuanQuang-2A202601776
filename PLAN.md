# PLAN — Lab 25: Tối ưu hóa Chi phí GPU (dạng Ticket)

> **AICB · Phase 2 · Track 2 (Infrastructure) · Day 25**
> File này chia toàn bộ lab thành **14 ticket** theo thứ tự làm việc.
> Mỗi ticket có: mục tiêu, việc cần làm, tiêu chí hoàn thành (DoD), và **“Bài học”** giải thích dễ hiểu.
> Tài liệu tham chiếu: [`README.md`](README.md) · [`Guide.md`](Guide.md) · [`Rubric.md`](Rubric.md)

---

## Bảng tổng hợp ticket

| ID | Ticket | Epic | Ưu tiên | Ước lượng | Phụ thuộc | Điểm |
|---|---|---|---|---|---|---|
| **SETUP-01** | Dựng môi trường & chạy `verify.py` | Setup | P0 | 20 phút | — | (nền tảng) |
| **SETUP-02** | Sinh & khám phá dữ liệu đầu vào | Setup | P0 | 30 phút | SETUP-01 | (nền tảng) |
| **M1-01** | Kiểm toán hiệu quả GPU (MFU/MBU/idle) | Missions | P0 | 60 phút | SETUP-02 | A |
| **M2-01** | Ba đòn bẩy chi phí Inference | Missions | P0 | 60 phút | SETUP-02 | A |
| **M3-01** | Chiến lược mua GPU (spot/reserved) | Missions | P0 | 60 phút | SETUP-02 | A |
| **M4-01** | Phân bổ chi phí & FOCUS export | Missions | P0 | 45 phút | SETUP-02 | A |
| **M5-01** | Báo cáo tổng hợp baseline vs optimized | Missions | P0 | 45 phút | M1→M4 | A + C |
| **QA-01** | Chạy full `verify.py` + `pytest` | QA | P0 | 20 phút | M5-01 | A + B |
| **EXT-01** | Cải thiện `recommend_tier()` | Extensions | P1 | 90 phút | M3-01 | D |
| **EXT-02** | Right-sizing theo MBU | Extensions | P1 | 90 phút | M1-01 | D |
| **EXT-03** | `cache_is_worth_it()` — kinh tế học của cache | Extensions | P1 | 90 phút | M2-01 | D |
| **EXT-04** | Ngân sách Reasoning ($ và Wh) | Extensions | P1 | 90 phút | M2-01 | D |
| **EXT-05** | Lập lịch nhận thức Carbon | Extensions | P1 | 90 phút | M3-01 | D |
| **DOC-01** | Viết write-up & nộp bài | Delivery | P0 | 60 phút | QA-01 + ≥2 EXT | C + D |

> **Đường tối thiểu để pass:** SETUP-01 → SETUP-02 → M1..M5 → QA-01 → chọn **2 ticket EXT** → DOC-01.

---

# EPIC 1 — Setup

## `SETUP-01` — Dựng môi trường & chạy verify

**Ưu tiên:** P0 · **Ước lượng:** 20 phút · **Phụ thuộc:** không

### Việc cần làm
```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python verify.py
```

### Tiêu chí hoàn thành (DoD)
- [ ] `which python` trỏ vào `.venv/bin/python`
- [ ] `pip list` có `pandas`, `matplotlib`, `pytest`
- [ ] `python verify.py` chạy được (chưa cần đủ 11/11 ở bước này)

### Bài học — Tại sao phải có virtualenv?

Hãy hình dung `.venv` là một **cái bếp riêng** cho món ăn này. Nếu bạn nấu chung bếp với 10 dự án khác, một dự án cần `pandas 1.x`, dự án khác cần `pandas 2.x` — chúng sẽ đá nhau và bạn mất cả buổi để gỡ.

Trong FinOps cũng cùng một tinh thần: **kết quả phải tái lập được**. Một báo cáo chi phí mà chạy lại ra số khác thì không ai dám ký duyệt. Virtualenv khóa phiên bản thư viện, `seed=25` khóa dữ liệu — hai thứ đó cộng lại cho bạn con số **luôn giống nhau** trên máy giảng viên và máy bạn.

> Lỗi hay gặp: `ModuleNotFoundError: No module named 'pandas'` → 99% là quên `source .venv/bin/activate`.

---

## `SETUP-02` — Sinh & khám phá dữ liệu đầu vào

**Ưu tiên:** P0 · **Ước lượng:** 30 phút · **Phụ thuộc:** SETUP-01

### Việc cần làm
```bash
python data/generate.py
```
Rồi mở từng file bằng pandas và trả lời: file này mô tả cái gì, cột nào quan trọng?

| File | Số dòng | Cột cần chú ý |
|---|---|---|
| `price_catalog.csv` | 7 GPU | `on_demand_hr`, `spot_hr`, `reserved_3yr_hr`, `peak_tflops_fp16`, `watts` |
| `gpu_telemetry.csv` | 11 GPU × 24h | `gpu_util_pct`, `achieved_tflops`, `achieved_bw_tbs` |
| `token_usage.csv` | 2,400 request | `route_tier`, `cached_input_tokens`, `is_batch`, `is_reasoning`, `team` |
| `workloads.csv` | 8 job | `hours_per_day`, `days`, `interruptible` |

### DoD
- [ ] 4 file CSV tồn tại trong `data/`
- [ ] Ghi ra được ≥1 GPU có `gpu_util_pct` cao nhưng `achieved_tflops` thấp
- [ ] Biết `interruptible=1` nghĩa là gì

### Bài học — Dữ liệu là hóa đơn, không phải log

Trong FinOps, mỗi dòng dữ liệu đều **quy ra tiền được**:

- `price_catalog.csv` = **bảng giá** → biết một giờ GPU tốn bao nhiêu
- `gpu_telemetry.csv` = **đồng hồ đo** → biết giờ đó bạn thực sự dùng được bao nhiêu
- `token_usage.csv` = **hóa đơn chi tiết** → biết tiền chảy về team nào
- `workloads.csv` = **hợp đồng thuê** → biết nên thuê tháng hay thuê năm

Ghép 4 thứ này lại, bạn có công thức nền của cả lab:
**Tiền = (giá × giờ) ÷ (số token phục vụ được)**. Vế trái là chi, vế phải là thu — FinOps chỉ là việc kéo giãn khoảng cách giữa hai vế đó.

---

# EPIC 2 — Missions

## `M1-01` — Kiểm toán hiệu quả GPU

**Ưu tiên:** P0 · **Ước lượng:** 60 phút · **Phụ thuộc:** SETUP-02 · **Module:** `finops/metrics.py`

### Việc cần làm
```bash
python missions/m1_efficiency_audit.py
```
Đọc 3 hàm: `compute_mfu()`, `flag_util_lies()`, `idle_waste_usd()`.

### DoD
- [ ] Xác định được `gpu-h100-4` là GPU “nói dối” (util 98%, MFU ~0.20)
- [ ] Tính được lãng phí idle theo `$/ngày` và quy ra `$/tháng`
- [ ] Trả lời được: idle chiếm bao nhiêu % tổng chi phí?

### Bài học — “GPU-Util lie”: chỉ số bận rộn không phải chỉ số hiệu quả

Tưởng tượng bạn thuê một **đầu bếp $100/giờ**. Cuối ca, quản lý báo: “Anh ấy bận 98% thời gian!” Nghe thì tuyệt. Nhưng nếu 80% thời gian đó anh ta chỉ **đứng chờ nguyên liệu từ kho**, thì bạn vẫn trả đủ $100/giờ để đổi lấy 1/5 số món ăn.

Đó chính xác là điều `nvidia-smi` làm:

| Chỉ số | Thực sự đo cái gì | Nói lên điều gì |
|---|---|---|
| `GPU-Util %` | Có kernel nào đang chạy trên GPU không | GPU **bận** |
| **MFU** | FLOPs thực đạt / FLOPs đỉnh | GPU **hiệu quả** |
| **MBU** | Băng thông thực / băng thông đỉnh | Có bị nghẽn **bộ nhớ** không |

`GPU-Util 98% + MFU 20%` = GPU bận rộn với việc **chờ bộ nhớ**, không phải việc tính toán. Nguyên nhân thường gặp: memory stall, kernel launch overhead, batch size quá nhỏ, data loader chậm.

**Tại sao MFU quan trọng với ví tiền:** MFU 20% nghĩa là bạn trả tiền H100 nhưng nhận hiệu năng của một GPU rẻ hơn 5 lần. Sửa MFU không cần mua thêm GPU — chỉ cần dùng đúng cái đang có.

> Mức tham chiếu: MFU tốt = **35–50%**. Dưới 30% mà util ≥ 90% → đỏ cờ.

---

## `M2-01` — Ba đòn bẩy chi phí Inference

**Ưu tiên:** P0 · **Ước lượng:** 60 phút · **Phụ thuộc:** SETUP-02 · **Module:** `finops/pricing.py`

### Việc cần làm
```bash
python missions/m2_inference_levers.py
```
Đọc `request_cost()`, `dollars_per_million()`, `discount_stack()`.

### DoD
- [ ] `$/1M-token` sau tối ưu thấp hơn baseline
- [ ] Savings nằm trong dải **60–95%**
- [ ] Giải thích được vì sao `discount_stack(batch=True, cache=1.0) = 0.05`

### Bài học — Chiết khấu **nhân** nhau, không **cộng** nhau

Ba đòn bẩy giảm chi phí inference:

| Đòn bẩy | Cơ chế | Mức giảm |
|---|---|---|
| **Cascade** | Câu hỏi dễ → model nhỏ; chỉ câu khó mới gọi model lớn | ~15× rẻ hơn cho phần được hạ cấp |
| **Prompt Caching** | Phần prompt lặp lại (system prompt, tài liệu) chỉ tính 10% giá | −90% trên phần cached |
| **Batch API** | Gom request không cần trả lời ngay, xử lý theo lô | −50% |

Điểm mấu chốt mà nhiều người tính sai: đây **không phải** phép cộng `50% + 90% = 140%`. Chúng **nhân** với nhau:

```
0.50 (batch)  ×  0.10 (cache)  =  0.05  →  bạn chỉ trả 5% giá gốc
```

Ví von: batch là **giảm giá 50%**, cache là **voucher giảm thêm 90% trên giá đã giảm**. Hai lần giảm liên tiếp trên phần còn lại, không phải trên giá gốc.

**Đánh đổi cần nhớ:** batch đổi **giá lấy độ trễ** — không dùng cho chatbot realtime, rất hợp cho việc gán nhãn, tóm tắt hàng loạt, đánh giá offline. Cache chỉ có lãi khi prefix được **đọc lại đủ nhiều** (xem `EXT-03`).

**Vì sao đo `$/1M-token` chứ không phải `$/GPU-giờ`:** `$/GPU-giờ` chỉ nói bạn **chi bao nhiêu**, không nói bạn **nhận được gì**. Hai team trả cùng $2.5/giờ nhưng một team phục vụ gấp 10 lần số token — chỉ đơn vị `$/1M-token` mới cho thấy sự khác biệt đó.

---

## `M3-01` — Chiến lược mua GPU

**Ưu tiên:** P0 · **Ước lượng:** 60 phút · **Phụ thuộc:** SETUP-02 · **Module:** `finops/pricing.py`

### Việc cần làm
```bash
python missions/m3_purchasing.py
```
Đọc `break_even_utilization()`, `recommend_tier()`, `spot_checkpoint_cost()`.

### DoD
- [ ] Có ít nhất 1 job được đề xuất `spot` và 1 job `reserved`
- [ ] Tổng chi phí sau tối ưu < chi phí on-demand
- [ ] Giải thích được vì sao `effective_hours > job_hours` khi chạy spot

### Bài học — Ba cách thuê GPU, giống ba cách thuê nhà

| Tier | Ví von | Khi nào dùng |
|---|---|---|
| **On-demand** | Thuê khách sạn theo đêm | Dùng thất thường, ít giờ/ngày |
| **Reserved** | Ký hợp đồng thuê 1–3 năm | Chạy đều, duty cycle cao |
| **Spot** | Ở ké — chủ nhà đòi là phải đi | Job **gián đoạn được** + có checkpoint |

**Điểm hòa vốn (break-even)** là con số quan trọng nhất của ticket này:

```
break_even_utilization = 1 − discount
Với reserved discount 45%  →  cần dùng ≥ 55% thời gian  =  13.2 giờ/ngày
```

Nghĩa là: reserved rẻ hơn 45% mỗi giờ, nhưng bạn **trả cả 24 giờ dù dùng hay không**. Chạy dưới 13.2 giờ/ngày thì phần trả cho giờ không dùng đã ăn hết khoản chiết khấu. Ký hợp đồng 3 năm trước khi tính con số này là cách phổ biến nhất để đốt tiền trong FinOps.

**Spot và cái giá của việc bị đuổi:** spot rẻ hơn ~40–60%, nhưng khi bị thu hồi bạn mất công việc từ checkpoint gần nhất và phải chạy lại. Vì thế `spot_checkpoint_cost()` trả về `effective_hours` **lớn hơn** `job_hours` — đó là số giờ thực phải trả sau khi cộng phần chạy lại + overhead ghi checkpoint. Spot chỉ thắng khi:

```
(giá spot × giờ hiệu dụng)  <  (giá on-demand × giờ thật)
```

Không có checkpoint thì spot không phải là chiến lược tiết kiệm — nó là một canh bạc.

---

## `M4-01` — Phân bổ chi phí & FOCUS export

**Ưu tiên:** P0 · **Ước lượng:** 45 phút · **Phụ thuộc:** SETUP-02 · **Module:** `finops/allocation.py`

### Việc cần làm
```bash
python missions/m4_allocation.py
head -5 outputs/focus_export.csv
```

### DoD
- [ ] Tag coverage đạt **85–100%**
- [ ] `chargeback_ready` trả về `True`
- [ ] `outputs/focus_export.csv` được tạo, có các cột FOCUS chuẩn

### Bài học — Từ “thấy” đến “thu tiền”: thang trưởng thành FinOps

```
Visibility  →  Showback  →  Chargeback
  (thấy)      (thông báo)    (thu tiền)
```

- **Visibility:** bạn biết công ty tiêu $50k/tháng cho GPU. Chưa ai thấy có trách nhiệm.
- **Showback:** bạn nói với team ML-Research: “tháng này các bạn tiêu $28k”. Không thu tiền, nhưng hành vi bắt đầu thay đổi — đây là bước tạo ra phần lớn khoản tiết kiệm thực tế.
- **Chargeback:** ngân sách của team thực sự bị trừ. Đây là mức kỷ luật cao nhất.

**Vì sao cần tag coverage ≥ 80% mới dám chargeback?** Nếu 30% chi phí không có tag, bạn buộc phải phân bổ mớ đó theo phỏng đoán. Team bị tính oan sẽ tranh cãi, và **một lần tranh cãi thắng là chương trình chargeback chết**. Uy tín số liệu là tài sản duy nhất của một FinOps engineer — tag trước, thu tiền sau.

**FOCUS là gì và vì sao quan trọng:** mỗi cloud provider đặt tên cột hóa đơn một kiểu (AWS gọi `UnblendedCost`, GCP gọi khác, Azure khác nữa). FOCUS là **chuẩn mở chung** của FinOps Foundation để mọi hóa đơn đổ về cùng một schema — nhờ đó công ty dùng 3 cloud vẫn cộng được một con số duy nhất mà không cần viết 3 ETL riêng.

---

## `M5-01` — Báo cáo tổng hợp baseline vs optimized

**Ưu tiên:** P0 · **Ước lượng:** 45 phút · **Phụ thuộc:** M1-01 → M4-01 · **Module:** `finops/report.py`, `finops/sustainability.py`

### Việc cần làm
```bash
python missions/m5_report.py
cat outputs/report.md
```

### DoD
- [ ] Tổng savings nằm trong dải **40–95%**
- [ ] `outputs/report.md` có đủ: baseline spend, optimized spend, % tiết kiệm, bảng từng lever
- [ ] `outputs/savings.png` hiển thị waterfall đúng 4 lever
- [ ] Có section **Sustainability** với năng lượng/truy vấn, carbon, vùng tốt nhất

### Bài học — Waterfall: kể câu chuyện tiết kiệm theo thứ tự

Báo cáo cộng dồn 4 lever:

| Lever | Nguồn | Bản chất |
|---|---|---|
| Inference (cascade/cache/batch) | M2 | Giảm giá mỗi token |
| Purchasing (spot/reserved) | M3 | Giảm giá mỗi giờ GPU |
| Right-size util-lies | M1 | Hạ cấp GPU trả tiền cao mà dùng không hết |
| Kill idle GPUs | M1 | Tắt hẳn thứ không ai dùng |

Biểu đồ waterfall quan trọng vì nó trả lời câu hỏi mà lãnh đạo thực sự hỏi: **“làm cái nào trước?”** Một cột tổng “tiết kiệm 46%” không giúp ai ra quyết định; bốn cột xếp theo độ lớn thì có. Nguyên tắc ưu tiên: **làm việc rẻ-nhanh-không rủi ro trước** (tắt idle GPU tốn 0 công sức), để dành việc cần cam kết dài hạn (reserved 3 năm) sau cùng.

**Phần Sustainability không phải để trang trí.** Điện là chi phí thật, và carbon đi kèm vị trí đặt máy:

- `europe-north1` (Na Uy, thủy điện) — vừa **rẻ** vừa **sạch** nhất
- `europe-central2` (Ba Lan) — ~660 gCO2/kWh, dơ nhất

Cùng một job training gián đoạn được, chỉ cần đổi vùng triển khai là giảm cả hóa đơn điện lẫn phát thải. Đây là trường hợp hiếm hoi mà **tiết kiệm tiền và giảm carbon đi cùng một hướng** — và cũng là lý do carbon-aware scheduling (`EXT-05`) đáng làm.

---

# EPIC 3 — QA

## `QA-01` — Chạy full verify + pytest

**Ưu tiên:** P0 · **Ước lượng:** 20 phút · **Phụ thuộc:** M5-01

### Việc cần làm
```bash
python missions/run_all.py
python verify.py     # kỳ vọng 11/11
pytest -q            # kỳ vọng 15 passed
```

### DoD
- [ ] `verify.py` → **11/11 checks passed** (30% điểm)
- [ ] `pytest -q` → **15 passed** (20% điểm)
- [ ] Không sửa file trong `tests/`

### Bài học — Test là hợp đồng, không phải thủ tục

`verify.py` kiểm tra **kết quả có hợp lý không** (savings trong dải 40–95%, coverage ≥ 85%), còn `pytest` kiểm tra **công thức có đúng không** (MFU tính đúng, chiết khấu nhân đúng).

Hai lớp này bắt hai loại lỗi khác nhau. Một công thức sai vẫn có thể cho ra con số “trông hợp lý” — chỉ unit test mới bắt được. Ngược lại, mọi công thức đều đúng nhưng ghép sai thứ tự trong mission thì chỉ verify mới thấy.

> **Cấm hardcode.** Rubric ghi rõ: sửa test hoặc nhét sẵn kết quả → mất toàn bộ điểm phần B, và phần báo cáo cũng sẽ lộ ra vì số liệu không khớp giữa `report.md` và output terminal.

**Bảng điểm nhanh:**

| verify | Điểm A | | pytest | Điểm B |
|---|---|---|---|---|
| 11/11 | 30 | | 15/15 | 20 |
| 10/11 | 25 | | 13–14 | 16 |
| 9/11 | 20 | | 10–12 | 12 |
| 8/11 | 15 | | 7–9 | 8 |

---

# EPIC 4 — Extensions (chọn ≥2, mỗi cái tối đa 10 điểm)

## `EXT-01` — Cải thiện `recommend_tier()`

**Ưu tiên:** P1 · **Ước lượng:** 90 phút · **File:** `finops/pricing.py`

### Việc cần làm
Viết lại `recommend_tier()` để tính thêm:
1. **Interruption rate theo GPU type** (H100 spot ít bị thu hồi hơn A10G)
2. **So sánh reserved 3yr vs 1yr** theo `job_days` thực tế

```python
def recommend_tier(hours_per_day, interruptible, reserved_discount=0.45,
                   gpu_type=None, job_days=None):
    ...
```

### DoD
- [ ] Chạy lại M3, in `savings_pct` **trước và sau**
- [ ] Giải thích được vì sao policy mới cho kết quả khác
- [ ] *(9–10đ)* Có ma trận đề xuất `GPU type × duty cycle × interruptible` + test tự viết

### Bài học — Chính sách đơn giản luôn để tiền trên bàn

Logic gốc chỉ nhìn 2 biến: `hours_per_day` và `interruptible`. Nó bỏ qua sự thật rằng **rủi ro spot không đồng đều** — GPU nào cũng bị thu hồi, nhưng tần suất khác nhau theo loại và theo vùng. Với GPU có interruption rate cao, phần chạy lại có thể nuốt hết khoản chiết khấu.

Và cam kết dài hơn không phải lúc nào cũng tốt hơn: reserved **3 năm** rẻ hơn 1 năm mỗi giờ, nhưng nếu job chỉ chạy 8 tháng thì bạn đang trả cho 28 tháng không dùng. Quy tắc: **thời hạn cam kết không được dài hơn độ chắc chắn của bạn về nhu cầu.**

---

## `EXT-02` — Right-sizing theo MBU

**Ưu tiên:** P1 · **Ước lượng:** 90 phút · **File:** `missions/m1_efficiency_audit.py`

### Việc cần làm
- Tính `$/GB-VRAM` cho từng GPU trong catalog
- Với GPU memory-bound (MBU thấp), đề xuất GPU thay thế rẻ hơn dựa trên `peak_bw_tbs`
- Tính monthly savings nếu right-size toàn bộ

### DoD
- [ ] Bảng so sánh: GPU hiện tại vs GPU đề xuất + lý do chọn
- [ ] Con số tiết kiệm `$/tháng` cụ thể

### Bài học — Roofline: workload của bạn nghẽn ở đâu?

**Arithmetic intensity** = số phép tính trên mỗi byte đọc từ bộ nhớ. So nó với **ridge point** của GPU (H100 ≈ 295 FLOP/byte):

| Giai đoạn LLM | Intensity | Chế độ | Cái gì là nút cổ chai |
|---|---|---|---|
| **Prefill** (đọc prompt) | ~455 | compute-bound | FLOPs |
| **Decode** (sinh từng token) | ~1–2 | **memory-bound** | Băng thông HBM |

Đây là lý do câu hỏi chấm điểm là *“tại sao không chỉ chọn GPU rẻ nhất theo `$/GPU-hr`?”*: nếu workload của bạn memory-bound, mua GPU nhiều FLOPs hơn **không tăng được token nào** — bạn trả tiền cho phần sức mạnh nằm không. Đúng chỉ số cần tối ưu lúc đó là `$/GB-VRAM` và `$/(TB/s băng thông)`.

Ví von: mua xe đua 500 mã lực để đi trong phố kẹt xe. Vấn đề không phải mã lực, mà là làn đường.

---

## `EXT-03` — `cache_is_worth_it()`

**Ưu tiên:** P1 · **Ước lượng:** 90 phút · **File:** `finops/pricing.py` + `missions/m2_inference_levers.py`

### Việc cần làm
```python
def cache_is_worth_it(avg_cache_reads: float,
                      write_cost_per_m: float,
                      read_discount: float = 0.10) -> bool:
    """Cache chỉ có lãi khi tổng tiết kiệm từ đọc > chi phí ghi."""
```
Áp dụng trong M2: chỉ cộng savings từ cache khi hàm trả về `True`.

### DoD
- [ ] Tính break-even số lần đọc cho từng model tier (nhỏ vs lớn)
- [ ] So sánh với `avg_cache_reads` thực tế trong `token_usage.csv`
- [ ] Có unit test tự viết

### Bài học — Cache không miễn phí

Prompt caching giảm 90% giá phần input đã cache — nhưng **ghi cache có chi phí** (một số nhà cung cấp tính tiền lưu trữ theo thời gian, hoặc tính phí ghi cao hơn giá input thường).

Phép tính break-even rất giống mua vé tháng xe buýt:

```
tiết kiệm mỗi lần đọc  ×  số lần đọc   >   chi phí ghi một lần
```

Cache một system prompt dùng 10.000 lần/ngày → lãi lớn. Cache một tài liệu dùng đúng 1 lần → **lỗ**. Bài học tổng quát của FinOps: mọi cơ chế tối ưu đều có chi phí cố định, và bạn phải kiểm tra khối lượng đủ lớn để khấu hao nó trước khi bật.

---

## `EXT-04` — Ngân sách Reasoning

**Ưu tiên:** P1 · **Ước lượng:** 90 phút · **File:** `missions/m2_inference_levers.py`, `missions/m5_report.py`

### Việc cần làm
- Tách riêng `$` và `Wh` cho `is_reasoning=1` vs `is_reasoning=0`
- In: reasoning chiếm **bao nhiêu % chi phí** với **bao nhiêu % traffic**
- Đề xuất routing rule + ước lượng tiết kiệm nếu cap reasoning xuống 10% traffic

```python
from finops.sustainability import wh_per_query
wh_per_query(tokens, is_reasoning=True)   # ~80× query thường
```

### DoD
- [ ] Có bảng `% traffic` vs `% chi phí` vs `% năng lượng`
- [ ] Có đề xuất routing rule cụ thể, định lượng được

### Bài học — Reasoning token là token đắt nhất bạn từng mua

Model reasoning “suy nghĩ” bằng cách sinh ra một chuỗi token nội bộ trước khi trả lời. Bạn trả tiền cho **toàn bộ** chuỗi đó, dù người dùng không bao giờ nhìn thấy nó. Năng lượng tiêu thụ có thể gấp **~74–86×** một truy vấn thường.

Điểm đau: reasoning thường chỉ chiếm phần nhỏ traffic nhưng chiếm phần lớn hóa đơn — một dạng phân bố Pareto rất kinh điển. Vì thế đòn bẩy ở đây không phải “tắt reasoning” mà là **định tuyến**: chỉ bật reasoning cho những request thực sự cần suy luận nhiều bước (toán, code, phân tích), tắt cho tra cứu và tóm tắt.

Đây cũng là ticket nối tiền với carbon rõ nhất: cắt reasoning không cần thiết giảm đồng thời `$` và `Wh`.

---

## `EXT-05` — Lập lịch nhận thức Carbon

**Ưu tiên:** P1 · **Ước lượng:** 90 phút · **File:** `missions/m3_purchasing.py` hoặc file mới

### Việc cần làm
```python
from finops.sustainability import REGION_CARBON, carbon_g, wh_per_query
# Với mỗi job interruptible=1:
#   1. carbon hiện tại (us-east-1)
#   2. carbon nếu chạy ở europe-north1
#   3. gCO2e tiết kiệm + % giảm
```

### DoD
- [ ] Bảng đủ 5 vùng: `$/kWh`, `gCO2/kWh`, chi phí điện thực, carbon thực
- [ ] Đề xuất vùng tối ưu theo 3 tiêu chí: rẻ nhất / sạch nhất / cân bằng nhất
- [ ] Có nhận xét về đánh đổi **latency**

### Bài học — Job gián đoạn được thì cũng di chuyển được

Nguyên tắc: **workload nào chịu được gián đoạn thì cũng chịu được đổi vùng.** Training có checkpoint không quan tâm nó đang chạy ở Virginia hay Na Uy — nhưng hóa đơn điện và lượng phát thải thì rất quan tâm.

Ngược lại, inference phục vụ người dùng **bị neo bởi latency**: đẩy nó sang vùng sạch nhất mà cách người dùng nửa vòng trái đất là đánh đổi trải nghiệm lấy carbon — thường không đáng.

Vì thế câu trả lời cho *“vùng nào tối ưu?”* là **“tùy bạn ưu tiên gì”**, và công việc của FinOps engineer không phải chọn hộ, mà là **đưa ra bảng đánh đổi đủ rõ để người khác chọn được**.

---

# EPIC 5 — Delivery

## `DOC-01` — Write-up & nộp bài

**Ưu tiên:** P0 · **Ước lượng:** 60 phút · **Phụ thuộc:** QA-01 + ≥2 ticket EXT

### Checklist nộp bài
```
[ ] python verify.py  →  11/11 checks passed
[ ] pytest -q         →  15 passed
[ ] outputs/report.md      (đủ section)
[ ] outputs/savings.png    (waterfall 4 lever)
[ ] outputs/focus_export.csv
[ ] ≥2 extension có kết quả đo lường
[ ] Bài viết 1–2 trang (.md hoặc .pdf)
```

### 5 câu bài viết phải trả lời
1. **Baseline vs Optimized** — chi phí và `$/1M-token` trước/sau, tiết kiệm bao nhiêu %?
2. **Phân tích từng lever** — lever nào đóng góp nhiều nhất, tại sao?
3. **GPU-Util Lie** — GPU nào, tác động tài chính ra sao?
4. **Extensions đã làm** — kết quả đo được, insight quan trọng nhất?
5. **Khuyến nghị** — nếu là FinOps lead, 3 hành động đầu tiên là gì?

### Bài học — Báo cáo là sản phẩm, không phải phụ lục

Rubric cho phần báo cáo **30 điểm** — bằng đúng phần verify tự động. Lý do rất thực tế: trong công việc thật, không ai trả lương cho bạn vì script chạy xanh. Họ trả lương vì **một quyết định được đưa ra dựa trên phân tích của bạn**.

Khác biệt giữa báo cáo 5 điểm và 10 điểm ở phần C.2:

| Mức | Đặc điểm |
|---|---|
| **Copy-paste** (<5) | Dán output terminal, không phân tích |
| **Đạt** (5–6) | Diễn giải lại output bằng lời |
| **Tốt** (7–8) | Nêu đúng vấn đề, đề xuất hợp lý, cơ chế còn sơ sài |
| **Xuất sắc** (9–10) | Chỉ ra **nguyên nhân gốc** (memory stall, kernel launch overhead), xếp hành động **theo ROI**, nối carbon với chi phí điện cụ thể |

Mẹo lấy điểm cao nhất: mỗi khi viết một con số, viết thêm một câu **“nên làm gì với con số này”**. Số liệu không kèm hành động là dữ liệu; số liệu kèm hành động là khuyến nghị.

---

## Phụ lục — 5 câu hỏi tự kiểm tra (Oral Check)

Trả lời trôi chảy 5 câu này nghĩa là bạn hiểu bản chất, không chỉ chạy script:

1. GPU-Util 98% có nghĩa GPU đang làm việc hiệu quả không? Tại sao?
2. Tại sao cần ≥80% tag coverage mới dám chargeback?
3. Nếu 70% workload là interruptible, bạn tối ưu purchasing thế nào?
4. `$/GPU-hr` và `$/1M-token` — khi nào hai con số này cho kết luận trái ngược?
5. Tại sao LLM decode là memory-bound còn prefill là compute-bound?

---

## Bonus (không chấm điểm)

| Thư mục | Nội dung | Học được gì |
|---|---|---|
| `bonus/litellm_tracker/` | Proxy LiteLLM giả lập + budget cap theo API key | Chặn chi tiêu **trước khi** hóa đơn về, thay vì phân tích sau |
| `bonus/local_model/` | Đo tok/s thực trên CPU | Đối chiếu simulation với số đo thật |
| `bonus/docker/` | Prometheus + Grafana dashboard chi phí GPU | Biến phân tích một lần thành **giám sát liên tục** |

---

> **Ghi nhớ cuối cùng:** giá GPU thay đổi hàng tháng — mọi con số trong lab là snapshot **tháng 6/2026**.
> Thứ bền vững theo thời gian là **phương pháp**: đo `$/token` chứ không phải `$/giờ`, tin MFU chứ không tin GPU-Util, nhân chiết khấu chứ không cộng, tính điểm hòa vốn trước khi cam kết, và gắn tag trước khi thu tiền.
