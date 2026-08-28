# M5-01 — Báo cáo tổng hợp baseline vs optimized

> Ticket `M5-01` trong [`PLAN.md`](../PLAN.md) · Chạy: `python missions/m5_report.py`
> Module: `finops/report.py`, `finops/sustainability.py` · Slide §1/§11
> Đầu ra: [`outputs/report.md`](report.md) + [`outputs/savings.png`](savings.png)
>
> *File này là phần **phân tích** đi kèm — `report.md` là deliverable do script sinh ra.*

---

## DoD — trạng thái

- [x] Tổng savings **46.1%** — trong dải yêu cầu 40–95%
- [x] `outputs/report.md` có baseline / optimized / % / bảng từng lever
- [x] `outputs/savings.png` — waterfall 4 lever
- [x] Section **Sustainability** có năng lượng, carbon, vùng tốt nhất
- [x] `pytest` → **15/15 passed** · `verify.py` → **11/11 checks passed**

---

## 1. Output của mission

```
Baseline spend:    $27,133
Optimized spend:   $14,626
Projected savings: $12,507  (46%)

| Lever                           | Savings (USD) |
|---------------------------------|---------------|
| Inference (cascade/cache/batch) |        $1,212 |
| Purchasing (spot/reserved)      |       $10,040 |
| Right-size util-lies            |          $655 |
| Kill idle GPUs                  |          $600 |
```

---

## 2. Bài học lớn nhất của M5: **% không phải là $**

Đây là chỗ số liệu đánh lừa mạnh nhất trong cả lab. So hai lever:

| Lever | Cắt được bao nhiêu **%** | Trên mẫu số nào | Ra bao nhiêu **$** |
|---|---|---|---|
| **Inference** | **82.6%** — ấn tượng nhất lab | $1,466/tháng | **$1,212** |
| **Purchasing** | 39.1% — khiêm tốn hơn nhiều | $25,667/tháng | **$10,040** |

**Purchasing tiết kiệm gấp 8.3 lần Inference, dù tỷ lệ cắt chỉ bằng một nửa.**

Lý do: mẫu số chênh nhau **17.5 lần**. Chi phí token inference của NimbusAI chỉ $48.87/ngày; chi phí thuê GPU cho 8 workload là $25,667/tháng. Cắt 82.6% của một khoản nhỏ vẫn ra số nhỏ.

**Phân bổ đóng góp thực tế:**

| Lever | $ | % tổng tiết kiệm |
|---|---|---|
| Purchasing | 10,040 | **80.3%** |
| Inference | 1,212 | 9.7% |
| Right-size util-lies | 655 | 5.2% |
| Kill idle GPUs | 600 | 4.8% |

> **Bài học vận hành:** khi ai đó khoe "chúng tôi giảm 82% chi phí LLM", câu hỏi đầu tiên phải là **"82% của bao nhiêu?"**. Một phần trăm ấn tượng trên một khoản nhỏ là thứ dễ đạt nhất và ít giá trị nhất. FinOps luôn ưu tiên theo **dollar tuyệt đối**, không theo phần trăm.

Điều này **không** có nghĩa M2 vô ích. Nó có nghĩa: với hồ sơ chi phí hiện tại của NimbusAI (nặng training, nhẹ inference), đòn bẩy mua sắm phải làm trước. Khi công ty scale inference lên gấp 20 lần, thứ tự này sẽ đảo ngược — và lúc đó cascade đã có sẵn.

---

## 3. Một lỗ hổng phương pháp trong cách M5 tính baseline

`report.md` nói tiết kiệm **46%**. Con số đó **được thổi lên** vì mẫu số thiếu.

```python
baseline = r2["baseline_daily"] * 30 + r3["on_demand_monthly"]
#        = $1,466 (token inference)  +  $25,667 (8 workload)  =  $27,133
```

Nhưng hai lever cuối lại đến từ **fleet telemetry của M1** — 11 GPU trong `gpu_telemetry.csv`, tổng **$15,394/tháng**:

| Lever | Nguồn dữ liệu | Có trong baseline? |
|---|---|---|
| Inference | `token_usage.csv` | ✅ có |
| Purchasing | `workloads.csv` | ✅ có |
| Right-size util-lies | `gpu_telemetry.csv` | ❌ **không** |
| Kill idle GPUs | `gpu_telemetry.csv` | ❌ **không** |

Tức là $1,255 tiết kiệm đang bị trừ khỏi một mẫu số **không chứa** những GPU sinh ra khoản tiết kiệm đó.

**Nếu tính nhất quán** (cộng cả fleet telemetry vào baseline):

| | Như M5 tính | Tính nhất quán |
|---|---|---|
| Baseline | $27,133 | $42,527 |
| Tiết kiệm | $12,507 | $12,507 |
| **%** | **46.1%** | **29.4%** |

Chênh **16.7 điểm phần trăm** chỉ vì chọn mẫu số.

**Nói vậy có nghĩa M5 sai không?** Không hẳn — `workloads.csv` và `gpu_telemetry.csv` là hai lát cắt của cùng một hạ tầng nhìn từ hai góc (kế hoạch job vs. đo lường thực tế), và lab không nối chúng bằng khóa chung. Nhưng **cách trình bày thì phải nói rõ điều đó**, nếu không người đọc hiểu rằng 46% là tỷ lệ trên toàn bộ hóa đơn GPU.

> Đây chính là kiểu lỗi mà `Rubric.md` C.3 nhắm tới — *"số liệu nhất quán giữa report.md và output của missions"*. Cách xử lý đúng cho `DOC-01`: nêu cả hai con số và giải thích mẫu số của từng cái.

---

## 4. Chi tiết hai lever từ M1

### Right-size util-lies — $655/tháng

```python
RIGHTSIZE_MAP = {"H100": "A100", "H200": "H100", "A100": "A10G", "A10G": "L4", "L4": "L4"}
```

| GPU | Hạ cấp | Chênh giá | $/tháng |
|---|---|---|---|
| `gpu-h100-4` | H100 → A100 | $0.71/h | $511 |
| `gpu-a10g-1` | A10G → L4 | $0.20/h | $144 |

**Vì sao hạ cấp là hợp lý:** ở `M1-01` ta tính được `gpu-h100-4` có MFU 0.194 × 990 TFLOPS = **~192 TFLOPS thực dùng** — thấp hơn cả peak của A100 (312 TFLOPS). Máy đó vốn dĩ không cần là H100.

**Hai giả định cần nói rõ:**
1. Công thức nhân `24 × 30` — giả định GPU chạy liên tục cả tháng.
2. Giả định hạ cấp **không làm giảm hiệu năng thực tế**. Đúng khi nút thắt là data loader hoặc kernel overhead (như phân tích ở M1); **sai** nếu workload thỉnh thoảng cần burst FLOPs.

Đây là lever cần đo trước khi làm — khác với lever "kill idle".

### Kill idle GPUs — $600/tháng

`gpu-h100-5` nằm không 8/24 giờ → $20/ngày × 30 = $600.

**Đây là lever ROI cao nhất trong cả báo cáo:** không cần profile, không cần đổi phần cứng, không rủi ro hiệu năng. Chỉ là scheduling. Nhưng nó xếp **chót bảng** theo dollar tuyệt đối — nên nếu chỉ đọc waterfall, bạn sẽ làm nó cuối cùng.

> **Waterfall xếp theo tiền, không xếp theo độ dễ.** Bảng ưu tiên hành động thật phải có thêm cột "công sức" và "rủi ro" — xem mục 6.

---

## 5. Sustainability — và một nhãn sai trong report

`report.md` in:

```
- Energy per query: 0.24 Wh
- Carbon per query: 0.091 gCO2e
- Cheapest+cleanest region: europe-north1
```

Bảng đầy đủ 5 vùng (`wh_per_query(800 token) = 0.24 Wh`):

| Region | $/kWh | gCO2/kWh | gCO2/query | $/1M query |
|---|---|---|---|---|
| us-east-1 | 0.120 | 380 | 0.0912 | $28.80 |
| us-west-2 | 0.070 | 120 | 0.0288 | $16.80 |
| **europe-north1** | 0.090 | **30** ← sạch nhất | 0.0072 | $21.60 |
| europe-central2 | 0.180 | 660 ← dơ nhất | 0.1584 | $43.20 |
| **us-east-wa** | **0.055** ← rẻ nhất | 90 | 0.0216 | **$13.20** |

**Nhãn "Cheapest+cleanest" không đúng.** Code chọn vùng bằng:

```python
"best_region": min(sustainability.REGION_CARBON, key=sustainability.REGION_CARBON.get)
```

— tức chỉ tối thiểu hóa **carbon**, không hề nhìn `REGION_PRICE_KWH`. `europe-north1` là **sạch nhất**, nhưng **`us-east-wa` rẻ hơn 39%** ($0.055 vs $0.090) và vẫn rất sạch (90 gCO2/kWh, hạng nhì).

Ba câu trả lời cho ba ưu tiên khác nhau:

| Ưu tiên | Vùng | Lý do |
|---|---|---|
| Sạch nhất | `europe-north1` | 30 gCO2/kWh (thủy điện Na Uy) |
| Rẻ nhất | `us-east-wa` | $0.055/kWh |
| **Cân bằng nhất** | **`us-east-wa`** | rẻ nhất **và** carbon hạng nhì |
| Tránh bằng mọi giá | `europe-central2` | đắt nhất **và** dơ nhất (660 gCO2) |

Chú ý `europe-central2` — **vừa đắt nhất vừa dơ nhất**. Không có đánh đổi nào ở đây cả; nó đơn giản là lựa chọn tệ trên mọi trục.

> `Rubric.md` C.1 cho **5 điểm** cho *"Phần Sustainability... vùng tốt nhất"*, và ghi rõ *"Thiếu hoặc **sai vùng tốt nhất**"* là không đạt. Báo cáo do script sinh ra đang dùng nhãn gây hiểu nhầm — `DOC-01` phải nêu đúng cả ba câu trả lời. Sửa nhãn này (hoặc thêm hàm chọn vùng có trọng số $ + CO2) là nội dung tự nhiên của `EXT-05`.

### Con số gây sốc nhất trong toàn lab

| | Traffic | Năng lượng |
|---|---|---|
| Request thường (`is_reasoning=0`) | 91.6% | 6.0% |
| **Request reasoning** (`is_reasoning=1`) | **8.4%** | **94.0%** |

```
Tổng năng lượng thực tế       : 31,675 Wh/ngày
Nếu không có request reasoning:  2,260 Wh/ngày   (÷14)
```

**8.4% traffic đang tiêu 94% điện.** Hệ số `REASONING_ENERGY_MULTIPLIER = 80` (khớp dải 74–86× trong dossier) nhân với việc request reasoning cũng dài hơn về token → kết quả cộng hưởng.

Quy ra tiền điện và carbon mỗi tháng:

| | us-east-1 (hiện tại) | us-east-wa | europe-north1 |
|---|---|---|---|
| Tiền điện | $114.03 | **$52.26** | $85.52 |
| Carbon | **361.1 kgCO2** | 85.5 kg | **28.5 kg** |

Chỉ đổi vùng: tiền điện −54%, carbon −92%. Không đổi một dòng code nào.

> Lưu ý về tỷ lệ: $114/tháng tiền điện là nhỏ so với $27,133 hóa đơn GPU — vì trong mô hình thuê cloud, tiền điện **đã nằm trong giá thuê**. Con số này có ý nghĩa khi bạn tự vận hành hạ tầng, hoặc khi báo cáo carbon (Scope 2). Đừng trình bày nó như một khoản tiết kiệm cộng thêm vào $12,507.

---

## 6. Bảng ưu tiên hành động — waterfall không đủ để ra quyết định

Waterfall xếp theo **dollar**. Quyết định thật cần thêm **công sức** và **rủi ro**:

| # | Hành động | $/tháng | Công sức | Rủi ro | Nguồn |
|---|---|---|---|---|---|
| **1** | Tắt `gpu-h100-5` trong 8h idle | 600 | rất thấp | ~0 | M1 |
| **2** | Chuyển 5 job interruptible sang spot | ~5,700 | thấp *(cần checkpoint)* | trung bình | M3 |
| **3** | Reserved cho 3 job infer duty 75–100% | ~4,350 | thấp | thấp *(nhưng cam kết dài)* | M3 |
| **4** | Bật batch cho traffic `eval`/offline | phần của 1,212 | rất thấp | ~0 | M2/M4 |
| **5** | Cascade routing small/large | phần lớn của 1,212 | trung bình *(cần đánh giá chất lượng)* | trung bình | M2 |
| **6** | Profile `gpu-h100-4`, sửa MFU hoặc hạ cấp | 511 | cao | trung bình | M1 |
| **7** | Bắt buộc tag `project` lúc tạo resource | 0 *(mở đường chargeback)* | thấp | ~0 | M4 |
| **8** | Chuyển job interruptible sang `us-east-wa` | ~$62 điện + −76% carbon | trung bình | thấp | M5 |

**Hai điều rút ra từ bảng này mà waterfall không cho thấy:**

- **#1 xếp chót về tiền nhưng phải làm đầu tiên** — 600$/tháng với công sức gần bằng 0 và rủi ro bằng 0. Không có lý do gì để chờ.
- **#3 tiết kiệm nhiều nhưng là cam kết 3 năm.** Xem lại `M3-01`: reserved chỉ hợp lý khi bạn chắc chắn nhu cầu kéo dài hết thời hạn. Ba job `infer` chạy `days=30` — đủ để tin, nhưng cần xác nhận roadmap sản phẩm trước khi ký.

---

## 7. Kiểm chứng — toàn bộ lab

```bash
$ pytest -q
...............                         [100%]
15 passed in 0.89s

$ python verify.py
  ...
  [PASS] M5 total savings in 40-95% band  (46.1%)
  [PASS] M5 report.md written
------------------------------------------------------------
  11/11 checks passed
```

| | Kết quả | Điểm rubric |
|---|---|---|
| `verify.py` | **11/11** | 30/30 |
| `pytest` | **15/15** | 20/20 |

---

## Kết nối sang ticket tiếp theo

| Phát hiện M5 | Dùng ở đâu |
|---|---|
| Purchasing = 80.3% tổng tiết kiệm dù % cắt thấp hơn | `DOC-01` — ưu tiên hành động |
| Baseline không gồm fleet telemetry → 46.1% vs 29.4% | `DOC-01` — trình bày trung thực mẫu số |
| Nhãn "cheapest+cleanest" chỉ đúng nửa (carbon) | `EXT-05` — hàm chọn vùng có trọng số $ + CO2 |
| Reasoning: 8.4% traffic / **94% năng lượng** | `EXT-04` — ngân sách reasoning |
| `us-east-wa` rẻ nhất + carbon hạng nhì | `EXT-05` — bảng đánh đổi 5 vùng |
| Rightsize giả định GPU chạy 24/7 và hạ cấp không mất hiệu năng | `EXT-02` — right-sizing theo MBU |
