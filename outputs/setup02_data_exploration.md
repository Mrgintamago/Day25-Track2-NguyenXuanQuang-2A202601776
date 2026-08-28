# SETUP-02 — Khám phá dữ liệu đầu vào

> Ticket `SETUP-02` trong [`PLAN.md`](../PLAN.md) · Sinh lại bằng `python missions/explore_data.py`
> Dữ liệu: `data/generate.py` với seed cố định = 25 → mọi lần chạy đều ra số giống nhau.

---

## DoD — trạng thái

- [x] 4 file CSV tồn tại trong `data/`
- [x] Ghi ra được GPU có `gpu_util_pct` cao nhưng `achieved_tflops` thấp → **`gpu-h100-4`** và **`gpu-a10g-1`**
- [x] Hiểu `interruptible=1` → **5/8 job** ứng cử spot + checkpoint

---

## 1. `price_catalog.csv` — Bảng giá (7 GPU)

| GPU | on-demand $/h | spot $/h | reserved 3yr $/h | spot −% | rsv3y −% | peak TFLOPS | BW TB/s | W | $/TFLOP-h | $/GB-VRAM-h |
|---|---|---|---|---|---|---|---|---|---|---|
| H100 | 2.50 | 1.50 | 1.40 | 40.0 | 44.0 | 990 | 3.35 | 700 | 2.525 | 0.0312 |
| H200 | 3.95 | 2.60 | 2.40 | 34.2 | 39.2 | 990 | 4.80 | 700 | 3.990 | 0.0280 |
| A100 | 1.79 | 1.10 | 1.00 | 38.5 | 44.1 | 312 | 2.00 | 400 | 5.737 | 0.0224 |
| A10G | 1.00 | 0.40 | 0.60 | 60.0 | 40.0 | 125 | 0.60 | 150 | 8.000 | 0.0417 |
| L4 | 0.80 | 0.35 | 0.45 | 56.2 | 43.8 | 121 | 0.30 | 72 | 6.612 | 0.0333 |
| B200 | 5.09 | 2.68 | 3.20 | 47.3 | 37.1 | 2250 | 8.00 | 1000 | 2.262 | 0.0265 |
| MI300X | 1.95 | 1.20 | 1.20 | 38.5 | 38.5 | 1307 | 5.30 | 750 | **1.492** | **0.0102** |

**Nhận xét:**

- **GPU đắt nhất theo giờ không phải GPU đắt nhất theo công việc.** B200 giá $5.09/h — gấp đôi H100 — nhưng `$/TFLOP-hr` chỉ 2.262 so với 2.525. Nếu workload của bạn thực sự compute-bound và dùng hết FLOPs, B200 **rẻ hơn** H100.
- **MI300X thắng cả hai chỉ số đơn giá** ($1.492/TFLOP-h, $0.0102/GB-VRAM-h). Đây là ứng cử viên đầu tiên cho `EXT-02` (right-sizing).
- **Chiết khấu reserved dao động 37–44%** → điểm hòa vốn `1 − discount` rơi vào khoảng **56–63% duty cycle**, tức ~13.5–15 giờ/ngày. Con số này dùng lại ở `M3-01`.
- **A10G và L4 có spot discount cao nhất** (60% và 56%) — GPU nhỏ ít bị tranh giành nên spot rẻ sâu hơn.

---

## 2. `gpu_telemetry.csv` — 11 GPU × 24 giờ (264 dòng)

Trung bình theo GPU, sắp xếp theo MFU tăng dần:

| gpu_id | type | workload | util % | **MFU** | MBU | power W |
|---|---|---|---|---|---|---|
| **gpu-h100-4** | H100 | train | **98.2** | **0.194** | 0.207 | 693.5 |
| gpu-a10g-0 | A10G | infer | 25.0 | 0.218 | 0.235 | 93.8 |
| gpu-a100-1 | A100 | infer | 28.0 | 0.236 | 0.247 | 256.0 |
| gpu-a100-0 | A100 | infer | 31.4 | 0.259 | 0.276 | 262.8 |
| gpu-h100-5 | H100 | train | 61.1 | 0.261 | 0.271 | 478.3 |
| **gpu-a10g-1** | A10G | infer | **96.9** | **0.268** | 0.302 | 147.7 |
| gpu-l4-0 | L4 | embed | 40.0 | 0.302 | 0.328 | 50.4 |
| gpu-h100-2 | H100 | train | 94.3 | 0.401 | 0.423 | 680.1 |
| gpu-h100-1 | H100 | train | 95.2 | 0.408 | 0.440 | 683.4 |
| gpu-h100-0 | H100 | train | 94.4 | 0.417 | 0.446 | 680.5 |
| gpu-h100-3 | H100 | train | 93.1 | 0.427 | 0.444 | 675.9 |

### GPU-Util lie (util ≥ 90% **và** MFU < 30%)

| GPU | util | MFU | Bạn trả | Bạn nhận |
|---|---|---|---|---|
| `gpu-h100-4` | 98.2% | 0.194 | $2.50/h | ~19% FLOPs của H100 |
| `gpu-a10g-1` | 96.9% | 0.268 | $1.00/h | ~27% FLOPs của A10G |

**Đọc bảng này thế nào:** 4 GPU H100 training "khỏe mạnh" (`gpu-h100-0..3`) có util ~94% và MFU **0.40–0.43** — đúng dải tốt 35–50%. `gpu-h100-4` có util **cao hơn tất cả** (98.2%) nhưng MFU **thấp nhất fleet** (0.194). Đây chính là bằng chứng trực tiếp rằng **util và MFU không cùng chiều**: cùng một loại GPU, cùng loại workload `train`, util nhích lên 4 điểm mà hiệu quả tính toán rớt hơn một nửa.

Chi tiết đáng chú ý: `power_w` của `gpu-h100-4` là **693.5W** — cao nhất fleet, sát trần 700W. Nó ăn điện nhiều nhất trong khi sinh ra ít FLOPs nhất. Đó là dấu hiệu kinh điển của **memory stall**: GPU liên tục bận chờ dữ liệu từ HBM, clock vẫn chạy, điện vẫn tốn, nhưng tensor core thì rỗi.

MBU của nó cũng chỉ 0.207 → **không phải bị nghẽn băng thông**. Cả hai chỉ số đều thấp trong khi util gần 100% ⇒ nghi vấn nghiêng về kernel launch overhead / batch size quá nhỏ / data loader chậm, chứ không phải giới hạn phần cứng.

### Giờ idle (util < 10%, tính theo **từng giờ**)

| GPU | Số giờ idle / 24 | Lãng phí |
|---|---|---|
| `gpu-h100-5` | 8 giờ | $20.00/ngày → **$600/tháng** |

> **Bẫy cần tránh:** nếu chỉ nhìn trung bình ngày, `gpu-h100-5` có util 61% — trông hoàn toàn bình thường và không GPU nào bị gắn cờ idle. Phải zoom xuống mức **từng giờ** mới thấy nó nằm không 8/24 giờ. Trung bình che giấu lãng phí; đây là lý do `idle_waste_usd()` nhận `idle_hours` chứ không nhận `avg_util`.

---

## 3. `token_usage.csv` — 2,400 request

```
requests = 2,400        tổng token = 7,533,027
cached_input / input    = 31.9%
is_batch = 1            = 17.3% traffic
is_reasoning = 1        =  8.4% traffic  nhưng 16.5% token
tag coverage            = 91.8%
```

| route_tier | requests | tokens |
|---|---|---|
| small | 1,902 (79.3%) | 5,984,315 |
| large | 498 (20.8%) | 1,548,712 |

| team | requests | tokens |
|---|---|---|
| assistant | 790 | 2,253,774 |
| eval | 415 | 1,825,366 |
| search | 629 | 1,808,367 |
| rag | 566 | 1,645,520 |

**Nhận xét:**

- **Reasoning là 8.4% request nhưng 16.5% token** — tức mỗi request reasoning "nặng" gấp ~2× request thường **chỉ tính token**. Cộng thêm hệ số năng lượng ~80×, đây là mục tiêu chính của `EXT-04`.
- **Cache hit 31.9%** — đủ cao để prompt caching có ý nghĩa, nhưng chưa phải mức "system prompt dùng lại 10.000 lần". `EXT-03` sẽ kiểm tra ngưỡng hòa vốn thực sự.
- **Batch mới chiếm 17.3%** — còn dư địa lớn, vì phần lớn traffic của team `eval` (415 request, đánh giá offline) về bản chất **không cần realtime**.
- **Tag coverage 91.8% > ngưỡng 80%** → cổng chargeback ở `M4-01` sẽ mở.
- `eval` chỉ đứng thứ 4 về số request nhưng **thứ 2 về token** (1.83M) — tokens/request cao gần gấp đôi. Xếp hạng theo số request sẽ cho kết luận sai; **luôn phân bổ chi phí theo token, không theo số lần gọi.**

---

## 4. `workloads.csv` — 8 job

| job_id | team | kind | GPU | n | h/ngày | ngày | duty % | interruptible | GPU-hours | on-demand $ | ứng viên |
|---|---|---|---|---|---|---|---|---|---|---|---|
| job-train-llm | rag | train | H100 | 8 | 20 | 14 | 83.3 | **1** | 2,240 | 5,600 | spot |
| job-train-embed | search | train | A100 | 4 | 10 | 5 | 41.7 | **1** | 200 | 358 | spot |
| job-finetune | assistant | train | H100 | 2 | 6 | 3 | 25.0 | **1** | 36 | 90 | spot |
| job-infer-chat | assistant | infer | A10G | 6 | 24 | 30 | 100.0 | 0 | 4,320 | 4,320 | reserved |
| job-infer-rag | rag | infer | A100 | 3 | 24 | 30 | 100.0 | 0 | 2,160 | 3,866 | reserved |
| job-infer-search | search | infer | L4 | 4 | 18 | 30 | 75.0 | 0 | 2,160 | 1,728 | reserved |
| job-dev-sandbox | eval | dev | A10G | 2 | 8 | 22 | 33.3 | **1** | 352 | 352 | spot |
| job-batch-eval | eval | infer | H100 | 1 | 3 | 30 | 12.5 | **1** | 90 | 225 | spot |

**Tổng chi phí on-demand: $16,539** · **5/8 job có `interruptible=1`**

**Nhận xét:**

- **`interruptible=1` nghĩa là job chịu được việc bị giết giữa chừng và chạy lại từ checkpoint.** Toàn bộ 3 job `train` + sandbox + batch-eval đều thuộc nhóm này. Đây vừa là điều kiện để chạy **spot** (`M3-01`), vừa là điều kiện để **đổi vùng triển khai** (`EXT-05`) — job không bị neo bởi latency người dùng.
- **Toàn bộ job `infer` đều `interruptible=0`** và duty cycle 75–100% → không thể spot, nhưng đều **vượt ngưỡng hòa vốn ~56%** ⇒ ứng viên reserved rõ ràng.
- **`job-train-llm` một mình chiếm $5,600 / $16,539 = 34% hóa đơn** và vừa interruptible vừa duty 83%. Đây là đòn bẩy đơn lẻ lớn nhất trong `M3-01`: chuyển sang spot H100 ($1.50 vs $2.50) là −40% trên một phần ba hóa đơn.
- **`job-batch-eval` duty chỉ 12.5%** — chạy 3 giờ/ngày. Nếu ai đó đã lỡ mua reserved cho nó thì đang trả 24 giờ để dùng 3 giờ. Đây là ví dụ trực quan cho bài học break-even.

---

## Kết nối sang ticket tiếp theo

| Phát hiện | Dùng ở đâu |
|---|---|
| `gpu-h100-4` MFU 0.194 + power 693W | `M1-01` — GPU-Util lie |
| `gpu-h100-5` idle 8/24 giờ = $600/tháng | `M1-01` — idle waste |
| cache 31.9% · batch 17.3% · small 79% | `M2-01` — 3 đòn bẩy inference |
| reserved discount 37–44% → break-even ~56–63% | `M3-01` — điểm hòa vốn |
| 5/8 job interruptible | `M3-01` spot · `EXT-05` carbon |
| tag coverage 91.8% | `M4-01` — cổng chargeback mở |
| reasoning 8.4% traffic / 16.5% token | `EXT-04` — ngân sách reasoning |
| MI300X rẻ nhất cả $/TFLOP-h và $/GB-VRAM-h | `EXT-02` — right-sizing theo MBU |
