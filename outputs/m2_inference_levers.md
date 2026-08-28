# M2-01 — Ba đòn bẩy chi phí Inference

> Ticket `M2-01` trong [`PLAN.md`](../PLAN.md) · Chạy: `python missions/m2_inference_levers.py`
> Module: `finops/pricing.py` · Slide §7

---

## DoD — trạng thái

- [x] `$/1M-token` giảm: **6.488 → 1.126** (−82.6%)
- [x] Savings **82.6%** — nằm trong dải yêu cầu **60–95%**
- [x] Giải thích được `discount_stack(batch=True, cache=1.0) = 0.05`
- [x] `pytest tests/test_pricing.py` → 5 passed
- [x] `verify.py` → 2 check M2 đều PASS

---

## 1. Output của mission

```
== M2 Inference Cost Levers ==
requests=2400  tokens=7,533,027
baseline  : $48.87/day   $6.488/1M-token
optimized : $8.48/day    $1.126/1M-token
savings   : 82.6%  (cascade + caching + batch)
discount stack (batch + 100% cache): 0.050 of naive
```

**Baseline nghĩa là gì:** triển khai ngây thơ — **mọi request đều gọi model lớn**, không cache, không batch. Đây không phải rơm dựng cho vui: rất nhiều team thật sự bắt đầu đúng như vậy, vì gọi model mạnh nhất là cách nhanh nhất để sản phẩm chạy được.

Giá dùng trong lab (`$/1M token`, input/output):

| Tier | input | output |
|---|---|---|
| `small` | $0.20 | $0.40 |
| `large` | $3.00 | $15.00 |

Chênh lệch **15× ở input, 37.5× ở output**. Con số này quyết định toàn bộ kết quả bên dưới.

---

## 2. Đòn bẩy nào đóng góp nhiều nhất?

Câu hỏi này phải trả lời bằng **ba góc nhìn khác nhau**, vì mỗi góc cho một thứ hạng khác nhau.

### Góc 1 — Cô lập: bật từng đòn bẩy một mình

| Đòn bẩy | Chi phí/ngày | Tiết kiệm | % |
|---|---|---|---|
| *(baseline)* | $48.87 | — | — |
| **Cascade** một mình | $11.48 | $37.40 | **76.5%** |
| Batch một mình | $40.64 | $8.24 | 16.9% |
| Cache một mình | $44.27 | $4.60 | 9.4% |

### Góc 2 — Cộng dồn theo thứ tự waterfall

| Bước | Chi phí/ngày | Giảm thêm | Tích lũy |
|---|---|---|---|
| baseline | $48.87 | — | — |
| **+ cascade** | $11.48 | −$37.40 | 76.5% |
| **+ cache** | $10.28 | −$1.20 | 79.0% |
| **+ batch** | $8.48 | −$1.79 | **82.6%** |

### Góc 3 — Đóng góp biên: bỏ từng đòn bẩy khỏi bộ đầy đủ

| Bỏ cái gì | Chi phí tăng lên | ⇒ đòn bẩy đó đang đáng giá |
|---|---|---|
| Bỏ **cascade** | $36.12 | **$27.64/ngày** |
| Bỏ **batch** | $10.28 | $1.79/ngày |
| Bỏ **cache** | $9.66 | $1.17/ngày |

### Kết luận: **Cascade thắng áp đảo, ở cả ba góc nhìn**

Cascade một mình đã lấy **76.5%** trong tổng 82.6%. Hai đòn bẩy còn lại cộng lại chỉ thêm **6.1 điểm phần trăm**.

**Vì sao?** Ba lý do cộng hưởng:

1. **Chênh lệch giá quá lớn.** small rẻ hơn large 15× ở input và **37.5× ở output**. Không đòn bẩy nào khác có hệ số cỡ đó — batch tối đa 2×, cache tối đa 10×.
2. **79.4% traffic đi được tier small** (1,902/2,400 request). Đòn bẩy tốt mà áp dụng được cho phần nhỏ traffic thì vẫn ra tiền nhỏ.
3. **Cascade tác động lên cả output token.** Cache **chỉ giảm giá phần input đã cache** — nó không đụng được vào output, mà output mới là phần đắt ($15 vs $3 ở tier large).

### Vì sao cache yếu hơn kỳ vọng ở dataset này?

Nghe "−90%" thì tưởng khủng khiếp, nhưng thực tế chỉ đóng góp 9.4% khi cô lập, và **1.17$/ngày** khi tính biên. Ba lý do:

- **Cache hit chỉ 31.9%** tổng input token, không phải 100%.
- Cache chỉ áp lên **input**. Trong dataset này output chiếm phần lớn hóa đơn ở tier large.
- **Thứ tự áp dụng làm loãng giá trị.** Cô lập, cache tiết kiệm $4.60. Nhưng khi cascade đã chạy trước và kéo hóa đơn từ $48.87 xuống $11.48, phần cache còn cắt được chỉ còn $1.20. Đây là hiệu ứng chung của waterfall: **đòn bẩy áp sau luôn trông nhỏ hơn giá trị thật của nó.**

> Bài học vận hành: đừng đọc waterfall như bảng xếp hạng giá trị. Cột đứng sau nhỏ vì phần bánh đã bị cột trước ăn mất, không phải vì nó kém. Muốn xếp hạng công bằng, dùng **đóng góp biên** (góc 3).

---

## 3. Vì sao `discount_stack(batch=True, cache_hit_frac=1.0) = 0.05`?

```python
def discount_stack(batch=False, cache_hit_frac=0.0,
                   batch_discount=0.50, cache_discount=0.10):
    cache_mult = cache_hit_frac * cache_discount + (1.0 - cache_hit_frac)
    batch_mult = batch_discount if batch else 1.0
    return cache_mult * batch_mult
```

Với `cache_hit_frac=1.0`: `cache_mult = 1.0 × 0.10 + 0 = 0.10`
Với `batch=True`: `batch_mult = 0.50`

```
0.10 × 0.50 = 0.05   →  trả 5% giá gốc  →  giảm 95%
```

**Điểm mấu chốt: chiết khấu NHÂN nhau, không CỘNG nhau.** `50% + 90%` không phải `140%` (vô nghĩa). Batch giảm một nửa, rồi cache giảm 90% **trên phần đã giảm đó**.

Ví von: sale 50% toàn cửa hàng, cầm thêm voucher giảm 90% tính trên **giá đã sale**. Áo $100 → $50 → $5.

Bảng đầy đủ:

| batch | cache hit | Hệ số | Bạn trả | Giảm |
|---|---|---|---|---|
| ✗ | 0% | 1.000 | 100% | 0% |
| ✓ | 0% | 0.500 | 50% | 50% |
| ✗ | 100% | 0.100 | 10% | 90% |
| ✓ | **31.9%** *(dataset thật)* | **0.356** | 35.6% | 64.4% |
| ✓ | 80% | 0.140 | 14% | 86% |
| ✓ | 100% | **0.050** | 5% | **95%** |

Chú ý dòng in đậm: con số **0.05** là **trần lý thuyết** khi cache hit đạt 100%. Dataset thật có cache hit 31.9% → hệ số thực tế là **0.356**, không phải 0.05. Đây là khác biệt giữa slide marketing và hóa đơn thật.

### Kiểm chứng bằng tay (Guide §5.3)

```python
baseline  = request_cost(1000, 200, 3.00, 15.00)                          # $0.0060
optimized = request_cost(1000, 200, 0.20, 0.40, cached_in=800, batch=True) # $0.0001
# ratio 0.0113  ->  giảm 98.9%
```

Một request đơn lẻ giảm **98.9%** — cao hơn con số fleet 82.6%, vì ví dụ này gộp cả cascade (15×/37.5×) **và** cache 80% **và** batch trên cùng một request. Trên dataset thật, không phải request nào cũng đủ điều kiện cả ba.

---

## 4. Khi nào **không nên** dùng batch API?

Batch đổi **giá lấy độ trễ**. Chiết khấu 50% đến kèm SLA hoàn thành tính bằng **giờ**, không phải mili-giây.

| Không dùng batch | Nên dùng batch |
|---|---|
| Chatbot / trợ lý realtime | Đánh giá offline, chấm điểm model |
| Autocomplete trong IDE | Gán nhãn / phân loại dữ liệu hàng loạt |
| Tìm kiếm tương tác | Sinh embedding cho toàn bộ corpus |
| Bất cứ thứ gì người dùng ngồi chờ | Tóm tắt hàng loạt, ETL đêm |

Nguyên tắc: **có người đang ngồi chờ trước màn hình không?** Có → không batch. Không → batch.

**Dataset hiện tại còn nhiều dư địa:** `is_batch=1` mới chỉ **17.3%** traffic. Riêng team `eval` có 415 request và bản chất công việc là đánh giá offline — gần như chắc chắn batch được. Đây là hành động chi phí thấp, rủi ro thấp, chưa ai làm.

---

## 5. Vì sao đo `$/1M-token` chứ không phải `$/GPU-giờ`?

| | Baseline | Optimized |
|---|---|---|
| Chi phí/ngày | $48.87 | $8.48 |
| **$/1M-token** | **6.488** | **1.126** |
| Token phục vụ | 7,533,027 | 7,533,027 |

`$/GPU-giờ` chỉ nói bạn **chi bao nhiêu**, không nói bạn **nhận được gì**. Hai team trả cùng $2.50/giờ H100, một team phục vụ gấp 10 lần token — chỉ đơn vị `$/1M-token` mới thấy được khác biệt đó.

Đây cũng là đơn vị nối M1 với M2: MFU thấp ở M1 làm **tử số** (chi phí hạ tầng) phình lên; thiếu cascade/cache/batch ở M2 cũng làm tử số phình lên. Cùng một mẫu số là token phục vụ. **`$/1M-token` là chỉ số duy nhất trong lab nhìn thấy được cả hai loại lãng phí cùng lúc.**

---

## 6. Kiểm chứng

```bash
$ pytest tests/test_pricing.py -q
.....                                   [100%]
5 passed in 0.02s

$ python verify.py | grep M2
  [PASS] M2 $/1M-token drops after optimization  (6.488 -> 1.126)
  [PASS] M2 inference savings in 60-95% band  (82.6%)
```

---

## Kết nối sang ticket tiếp theo

| Phát hiện M2 | Dùng ở đâu |
|---|---|
| Inference: $48.87 → $8.48/ngày (−82.6%) | `M5-01` lever "Inference" |
| Cache hit thật 31.9% → hệ số 0.356, không phải 0.05 | `EXT-03` — cache có đáng không? |
| Reasoning = 8.4% traffic nhưng **16.5% chi phí optimized** | `EXT-04` — ngân sách reasoning |
| Batch mới 17.3% traffic, team `eval` chưa batch | `EXT-04` / khuyến nghị vận hành |
| Cascade là đòn bẩy mạnh nhất (76.5%) | `DOC-01` — ưu tiên hành động #1 |
