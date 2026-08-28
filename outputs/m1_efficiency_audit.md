# M1-01 — Kiểm toán hiệu quả GPU

> Ticket `M1-01` trong [`PLAN.md`](../PLAN.md) · Chạy: `python missions/m1_efficiency_audit.py`
> Module: `finops/metrics.py` · Slide §5

---

## DoD — trạng thái

- [x] Xác định GPU "nói dối" → **`gpu-h100-4`** (util 98.2%, MFU 0.194) và **`gpu-a10g-1`**
- [x] Lãng phí idle: **$20.00/ngày → $600/tháng**
- [x] Idle chiếm **3.9%** tổng chi phí fleet; cộng cả util-lie thì **11.2%** ($1,723/tháng)
- [x] `pytest tests/test_metrics.py` → 4 passed
- [x] `verify.py` → 2 check M1 đều PASS

---

## 1. Output của mission

```
== M1 Efficiency Audit ==
GPU           type     util%    MFU    MBU  idle_h
gpu-h100-4    H100      98.2  0.194  0.207       0
gpu-a10g-0    A10G      25.0  0.218  0.235       0
gpu-a100-1    A100      28.0  0.236  0.247       0
gpu-a100-0    A100      31.4  0.259  0.276       0
gpu-h100-5    H100      61.1  0.261  0.271       8
gpu-a10g-1    A10G      96.9  0.268  0.302       0
gpu-l4-0      L4        40.0  0.302  0.328       0
gpu-h100-2    H100      94.3  0.401  0.423       0
gpu-h100-1    H100      95.2  0.408  0.440       0
gpu-h100-0    H100      94.4  0.417  0.446       0
gpu-h100-3    H100      93.1  0.427  0.444       0

GPU-Util LIES (util>=90% but MFU<30%): ['gpu-h100-4', 'gpu-a10g-1']
Idle waste (1 day): $20.00  ->  $600/month
```

---

## 2. Trả lời 3 câu hỏi phân tích (Guide §4.3)

### Câu 1 — GPU nào có `GPU-Util` cao nhất? MFU của nó là bao nhiêu?

**`gpu-h100-4`: util 98.2% — cao nhất fleet. MFU 0.194 — thấp nhất fleet.**

Hai thứ hạng này ngược chiều nhau hoàn toàn, và đó chính là toàn bộ bài học của M1.

Có một nhóm đối chứng rất sạch để so: 4 con H100 khác (`gpu-h100-0..3`) cũng chạy workload `train`, cũng cùng loại GPU, util ~93–95%, MFU **0.401–0.427** (trung bình **0.413**, đúng dải khỏe mạnh 35–50%).

| | `gpu-h100-0..3` | `gpu-h100-4` |
|---|---|---|
| util | 93–95% | **98.2%** (cao hơn) |
| MFU | 0.401–0.427 | **0.194** (thấp hơn 2.1×) |
| power | 675–683W | **693.5W** (cao nhất) |

Cùng phần cứng, cùng loại việc, util nhích lên 4 điểm mà hiệu quả tính toán rớt hơn một nửa. Nếu `nvidia-smi` là thước đo hiệu quả thật thì điều này không thể xảy ra.

### Câu 2 — Tại sao `GPU-Util 98%` có thể đi kèm `MFU 20%`?

Vì hai chỉ số **đếm hai thứ khác nhau**:

| Chỉ số | Định nghĩa thật | Trả lời câu hỏi |
|---|---|---|
| `GPU-Util %` | % khoảng thời gian có **ít nhất một kernel** đang chạy trên GPU | GPU có **bận** không? |
| **MFU** | FLOPs thực đạt / FLOPs đỉnh lý thuyết | GPU có **hiệu quả** không? |

Một kernel đang chạy nhưng dành phần lớn chu kỳ để **chờ dữ liệu từ HBM** vẫn được tính là "đang hoạt động". Util nhìn thấy 98%; tensor core thì rỗi.

**Bằng chứng trong dữ liệu — cơ chế nào gây ra?**

`gpu-h100-4` có MFU 0.194 **và** MBU 0.207. Cả hai đều thấp. Đây là chi tiết quyết định:

- Nếu **MBU cao, MFU thấp** → bị nghẽn băng thông, workload memory-bound. Cách chữa: đổi GPU băng thông cao hơn, hoặc gộp batch lớn hơn.
- Ở đây **cả hai đều thấp** → GPU không bị nghẽn FLOPs, cũng không bị nghẽn băng thông. Nó đơn giản là **không được cho đủ việc để làm**.

Nguyên nhân gốc điển hình cho pattern này:

1. **Kernel launch overhead** — quá nhiều kernel nhỏ; CPU không kịp đẩy lệnh, GPU xong việc rồi ngồi chờ lệnh kế tiếp. Mỗi khe chờ ngắn vẫn được tính vào util.
2. **Batch size quá nhỏ** — không đủ song song để lấp hết SM.
3. **Data loader chậm / nghẽn I/O** — GPU chờ batch tiếp theo từ CPU hoặc disk.
4. **Đồng bộ hóa trong training phân tán** — chờ all-reduce từ rank chậm nhất.

Chỉ số `power_w = 693.5W` (cao nhất fleet, sát trần 700W) củng cố kết luận: **clock chạy hết công suất, điện tốn hết mức, nhưng công việc hữu ích thì không có.** Bạn đang trả tiền điện cho việc chờ đợi.

> Ví von: đầu bếp $100/giờ "bận 98%" — nhưng 80% thời gian đó đứng chờ nguyên liệu từ kho. Bếp vẫn nóng, hóa đơn gas vẫn chạy, món ăn thì không ra.

### Câu 3 — Lãng phí idle bao nhiêu `$/tháng`? Chiếm bao nhiêu % tổng chi phí?

| | Giá trị |
|---|---|
| Chi phí fleet (11 GPU × 24h, on-demand) | **$513.12/ngày** → **$15,394/tháng** |
| Lãng phí idle (`gpu-h100-5`, 8/24 giờ) | **$20.00/ngày** → **$600/tháng** |
| **Idle chiếm** | **3.90%** tổng chi phí |

**Điểm quan trọng về cách phát hiện idle:** không GPU nào có util **trung bình ngày** dưới 10%. `gpu-h100-5` trung bình 61% — nhìn qua hoàn toàn bình thường. Chỉ khi zoom xuống **từng giờ** mới thấy nó nằm không 8/24 giờ.

Đây là lý do `idle_waste_usd()` nhận tham số `idle_hours` chứ không nhận `avg_util`:

```python
def idle_waste_usd(idle_hours: float, on_demand_hr: float) -> float:
    return max(0.0, idle_hours) * max(0.0, on_demand_hr)
```

**Trung bình che giấu lãng phí.** Một GPU chạy 100% trong 16 giờ và 0% trong 8 giờ có cùng con số trung bình với GPU chạy đều 67% cả ngày — nhưng chỉ cái đầu tiên có 8 giờ để bạn tắt đi và lấy lại $600/tháng.

---

## 3. Tác động tài chính của "GPU-Util lie"

Idle mới chỉ là 3.9%. Phần đắt hơn nằm ở chỗ khó thấy hơn: **tiền trả cho FLOPs đã thuê nhưng không nhận được.**

Lấy MFU của nhóm H100 khỏe mạnh (**0.413**) làm chuẩn tham chiếu, và 0.35 cho A10G:

| GPU | Chi phí/ngày | MFU | Chuẩn | Tiền trả cho FLOPs không nhận được |
|---|---|---|---|---|
| `gpu-h100-4` | $60.00 | 0.194 | 0.413 | **$31.80/ngày** → **$954/tháng** |
| `gpu-a10g-1` | $24.00 | 0.268 | 0.35 | $5.64/ngày → $169/tháng |
| | | | **Tổng** | **$37.44/ngày (7.3% fleet)** |

**Cộng cả hai loại lãng phí:**

| Loại | $/ngày | % fleet | $/tháng |
|---|---|---|---|
| Idle GPU | 20.00 | 3.9% | 600 |
| Util-lie (FLOPs không nhận) | 37.44 | 7.3% | 1,123 |
| **Tổng** | **57.44** | **11.2%** | **$1,723** |

**11.2% hóa đơn GPU đang bốc hơi mà không cần mua thêm một GPU nào để lấy lại.** Và điều đáng nói là toàn bộ khoản này **vô hình trên dashboard `nvidia-smi`** — `gpu-h100-4` hiển thị 98% util, con số đẹp nhất fleet.

**Thứ tự ưu tiên xử lý (ROI giảm dần):**

| # | Hành động | Công sức | Thu về |
|---|---|---|---|
| 1 | Tắt `gpu-h100-5` trong 8 giờ idle (hoặc autoscale) | Rất thấp — chỉ là scheduling | $600/tháng, rủi ro ~0 |
| 2 | Profile `gpu-h100-4` (nsys/nsight) tìm nguyên nhân stall | Trung bình — cần kỹ sư | tối đa $954/tháng |
| 3 | Nếu không sửa được MFU → hạ cấp `gpu-h100-4` xuống GPU rẻ hơn | Trung bình | phần chênh giá |
| 4 | `gpu-a10g-1` — số tiền nhỏ, để sau | Thấp | $169/tháng |

Lưu ý ở mục 3: nếu MFU không sửa được thì **GPU đó vốn dĩ không cần là H100**. MFU 0.194 × 990 TFLOPS = ~192 TFLOPS thực dùng — thấp hơn cả peak của A100 (312). Đây chính là cầu nối sang `EXT-02` (right-sizing) và lever "Right-size util-lies" ở `M5-01`.

---

## 4. Roofline model (Guide §4.4)

```python
from finops.metrics import roofline_regime
roofline_regime(1.5, 295)   # 'memory-bound'   <- LLM decode
roofline_regime(455, 295)   # 'compute-bound'  <- LLM prefill
```

**Arithmetic intensity** = FLOP thực hiện trên mỗi byte đọc từ bộ nhớ. So với **ridge point** của GPU (H100 ≈ 295 FLOP/byte ở BF16):

| Giai đoạn | Intensity | Chế độ | Nút cổ chai | Chỉ số cần theo dõi |
|---|---|---|---|---|
| **Prefill** (đọc prompt) | ~455 | compute-bound | FLOPs | **MFU** |
| **Decode** (sinh từng token) | ~1–2 | **memory-bound** | Băng thông HBM | **MBU** |

Decode phải đọc **toàn bộ trọng số model** từ HBM để sinh ra **đúng một token**. Tỷ lệ tính-toán/dữ-liệu cực thấp → nghẽn hoàn toàn ở băng thông, không phải ở FLOPs.

**Hệ quả cho ví tiền:** với workload decode, mua GPU nhiều FLOPs hơn **không sinh thêm một token nào**. Đây là lý do prefill/decode disaggregation (tách hai giai đoạn lên hai loại GPU khác nhau) tiết kiệm được tiền — và là lý do câu hỏi chấm điểm của `EXT-02` là *"tại sao không chỉ chọn GPU rẻ nhất theo `$/GPU-hr`?"*.

Nhìn lại bảng M1: tất cả GPU `infer` trong fleet (`a10g-0/1`, `a100-0/1`) đều có MBU 0.235–0.302 — thấp so với mục tiêu ~0.60 cho decode. Chúng chưa khai thác hết băng thông đã trả tiền.

---

## 5. Kiểm chứng

```bash
$ pytest tests/test_metrics.py -q
....                                    [100%]
4 passed in 0.02s

$ python verify.py | grep M1
  [PASS] M1 flags the GPU-Util lie (gpu-h100-4)  (['gpu-h100-4', 'gpu-a10g-1'])
  [PASS] M1 detects idle waste  ($20.0/day)
```

---

## Kết nối sang ticket tiếp theo

| Phát hiện M1 | Dùng ở đâu |
|---|---|
| `gpu-h100-4` MFU 0.194, MBU 0.207, 693W | `M5-01` lever "Right-size util-lies" |
| `gpu-h100-5` idle 8/24h = $600/tháng | `M5-01` lever "Kill idle GPUs" |
| MFU 0.194 × 990 = 192 TFLOPS < peak A100 | `EXT-02` — right-sizing |
| Toàn bộ GPU infer có MBU 0.235–0.302 (mục tiêu ~0.60) | `EXT-02` — chọn GPU theo băng thông |
| Điện 693W cho công việc vô ích | `M5-01` — section Sustainability |
