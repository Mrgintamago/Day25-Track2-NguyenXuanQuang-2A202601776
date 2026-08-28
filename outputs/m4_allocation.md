# M4-01 — Phân bổ chi phí & FOCUS export

> Ticket `M4-01` trong [`PLAN.md`](../PLAN.md) · Chạy: `python missions/m4_allocation.py`
> Module: `finops/allocation.py` · Slide §10

---

## DoD — trạng thái

- [x] Tag coverage **91.8%** — trong dải yêu cầu 85–100%
- [x] `chargeback_ready` → **True** (≥ 80%)
- [x] `outputs/focus_export.csv` được tạo (50 dòng + header)
- [x] `pytest tests/test_allocation.py` → 3 passed
- [x] `verify.py` → 2 check M4 đều PASS

---

## 1. Output của mission

```
== M4 Cost Allocation ==
cost by team ($/day):
  assistant    $    2.59
  search       $    2.49
  eval         $    1.79
  rag          $    1.60
tag coverage: 92%  ->  chargeback ready? True
FOCUS export -> outputs/focus_export.csv (50 rows)
```

Tổng $8.47 ≈ **$8.48/ngày** — khớp với chi phí optimized của `M2-01`. Đây là kiểm tra đầu tiên phải làm với mọi báo cáo phân bổ: **tổng các phần phải bằng hóa đơn**. Nếu lệch, bạn đang tính phí sai cho ai đó.

---

## 2. Trả lời 3 câu hỏi phân tích (Guide §7.4)

### Câu 1 — Team nào tốn nhiều nhất?

| Team | requests | % req | tokens | % token | $/ngày | **% chi phí** | **$/1M-token** |
|---|---|---|---|---|---|---|---|
| assistant | 790 | 32.9% | 2,253,774 | 29.9% | 2.59 | **30.6%** | 1.150 |
| search | 629 | 26.2% | 1,808,367 | 24.0% | 2.49 | **29.4%** | 1.379 |
| eval | 415 | 17.3% | 1,825,366 | 24.2% | 1.79 | **21.2%** | 0.983 |
| rag | 566 | 23.6% | 1,645,520 | 21.8% | 1.60 | **18.9%** | 0.975 |

**`assistant` đứng đầu với 30.6%** — nhưng con số thú vị nằm ở chỗ khác: **thứ hạng đổi tùy bạn đếm cái gì.**

| Xếp theo | Hạng 1 | Hạng 2 | Hạng 3 | Hạng 4 |
|---|---|---|---|---|
| Số request | assistant | search | rag | **eval** |
| Token | assistant | **eval** | search | rag |
| **Chi phí** | assistant | search | **eval** | rag |

`eval` xếp **chót về số request** (17.3%) nhưng **hạng 2 về token** (24.2%) và hạng 3 về tiền. Nếu chia hóa đơn theo số lần gọi API — cách nhiều công ty làm vì nó dễ đếm — `eval` sẽ bị tính phí thiếu và ba team kia gánh hộ.

> **Nguyên tắc:** phân bổ theo **đơn vị sinh ra chi phí**, không phải theo đơn vị dễ đếm. Với LLM, đơn vị đó là token (và token output đắt hơn input), không phải số request.

### Câu 2 — Tag coverage đủ để chargeback không?

**91.8% ≥ ngưỡng 80% → cổng mở.** Nhưng nhìn kỹ hơn:

```
row thiếu tag `team`    : 0    / 2,400
row thiếu tag `project` : 197  / 2,400   (8.2%)
chi phí không phân bổ được: $0.71/ngày = 8.3% = ~$21/tháng
```

Toàn bộ phần thiếu nằm ở **`project`, không phải `team`**. Điều này quan trọng về mặt vận hành:

- **Showback theo team vẫn chính xác 100%** — mọi dòng đều có team. Bạn có thể gửi hóa đơn cho từng team ngay hôm nay.
- **Chargeback theo project thì không** — 8.3% chi phí rơi vào `(untagged)`, đủ để một product manager phản đối con số của dự án mình.

Bảng phân bổ theo project cho thấy rõ:

| Project | $/ngày | % |
|---|---|---|
| chat | 2.44 | 28.7% |
| web-search | 2.27 | 26.8% |
| nightly-eval | 1.62 | 19.0% |
| doc-qa | 1.45 | 17.1% |
| **(untagged)** | **0.71** | **8.3%** |

**Độ nhạy của ngưỡng:**

| Ngưỡng | `chargeback_ready` |
|---|---|
| 80% *(mặc định)* | ✅ True |
| 90% | ✅ True |
| 95% | ❌ False |
| 99% | ❌ False |

Coverage 91.8% chỉ hơn ngưỡng 80% một khoảng an toàn vừa phải, và **trượt ngay khi nâng chuẩn lên 95%**. Đây không phải con số để tự mãn — nó là con số "vừa đủ qua cửa".

**Vì sao ngưỡng 80% tồn tại?** Nếu 20% chi phí không có tag, bạn buộc phải phân bổ mớ đó theo phỏng đoán (chia đều? theo tỷ lệ? theo headcount?). Team bị tính oan sẽ tranh cãi — và **một lần tranh cãi thắng là chương trình chargeback chết**. Uy tín số liệu là tài sản duy nhất của FinOps engineer: tag trước, thu tiền sau.

### Câu 3 — Vì sao FOCUS quan trọng khi dùng nhiều cloud?

Mỗi nhà cung cấp đặt tên cột hóa đơn một kiểu: AWS gọi `UnblendedCost`, GCP gọi `cost`, Azure gọi `CostInBillingCurrency`. Cùng một khái niệm, ba cái tên, ba schema, ba đơn vị thời gian.

**FOCUS** (FinOps Open Cost & Usage Specification, do FinOps Foundation duy trì) chuẩn hóa tất cả về một schema:

```csv
BillingAccountId,ChargePeriodStart,ServiceCategory,ServiceName,ResourceId,BilledCost,BillingCurrency,team,project
nimbusai-prod,2026-06-01,AI and Machine Learning,gpu-inference,,0.0009,USD,rag,doc-qa
```

| Cột | Vai trò |
|---|---|
| `BillingAccountId` | Tài khoản chịu chi phí |
| `ChargePeriodStart` | Kỳ tính phí — cho phép cộng dồn theo thời gian nhất quán |
| `ServiceCategory` | Nhóm dịch vụ chuẩn (`AI and Machine Learning`) |
| `BilledCost` | Chi phí thực tính — **cùng một định nghĩa trên mọi vendor** |
| `Tags.team` / `Tags.project` | Chiều phân bổ |

Không có FOCUS, công ty dùng 3 cloud phải viết **3 pipeline ETL riêng**, và mỗi lần vendor đổi format là hỏng một cái. Có FOCUS, bạn viết một dashboard chạy trên mọi nguồn.

**Một lỗi dữ liệu trong export hiện tại:** cột `ResourceId` **rỗng toàn bộ**. Xem code:

```python
"ResourceId": r.get("resource_id", r.get("gpu_id", "")),
```

Dữ liệu `token_usage.csv` không có `resource_id` lẫn `gpu_id`, nên rơi về chuỗi rỗng. Hệ quả thực tế: bạn biết **team nào** tiêu tiền nhưng không biết **tài nguyên nào** sinh ra chi phí — không thể truy ngược từ hóa đơn về một endpoint hay deployment cụ thể. Đây là kiểu lỗ hổng tag điển hình: schema thì đúng, dữ liệu thì rỗng, và không có test nào bắt được.

---

## 3. Thang trưởng thành: repo đang ở đâu?

```
Visibility  →  Showback  →  Chargeback
  (thấy)      (thông báo)    (thu tiền)
```

| Mức | Nghĩa là gì | Trạng thái NimbusAI |
|---|---|---|
| **Visibility** | Biết tổng chi $8.48/ngày | ✅ Xong từ M2 |
| **Showback** | Nói với từng team con số của họ | ✅ Sẵn sàng — team coverage 100% |
| **Chargeback** | Trừ thật vào ngân sách team | ⚠️ Được theo **team**, chưa nên theo **project** (8.3% untagged) |

**Vì sao showback tạo ra phần lớn khoản tiết kiệm thực tế:** trước showback, chi phí GPU là "vấn đề của công ty" — không ai thấy mình có trách nhiệm. Sau showback, team `search` nhìn thấy `$/1M-token` của mình là **1.379 — cao nhất trong 4 team** và tự đi tìm lý do. Không cần cưỡng chế gì cả.

### Vì sao `$/1M-token` của các team lệch nhau?

| Team | % dùng tier `large` | % batch | % reasoning | $/1M |
|---|---|---|---|---|
| search | 21.8% | 0% | 0% | **1.379** |
| assistant | 21.9% | 0% | 0% | 1.150 |
| eval | 20.2% | **100%** | **48.4%** | **0.983** |
| rag | 18.4% | 0% | 0% | 0.975 |

Hai quan sát:

- **`eval` batch 100% traffic** → được giảm 50% toàn bộ hóa đơn. Dù có tỷ lệ reasoning cao nhất (48.4%) và token/request nặng nhất, nó vẫn có `$/1M` gần thấp nhất. **Batch bù được cả reasoning.**
- **`search` đắt nhất** dù tỷ lệ `large` gần bằng `assistant` và không có reasoning. Nguyên nhân nằm ở cấu trúc request (tỷ lệ output/input và cache hit), không ở tier — đúng loại câu hỏi mà showback khiến team tự đi tìm.

Đây cũng là khuyến nghị vận hành rõ nhất từ M4: **`search` và `assistant` chưa batch một request nào**. Không phải toàn bộ traffic của họ batch được, nhưng con số 0% nghĩa là chưa ai thử tách phần nào không cần realtime.

---

## 4. Kiểm chứng

```bash
$ pytest tests/test_allocation.py -q
...                                     [100%]
3 passed in 0.02s

$ python verify.py | grep M4
  [PASS] M4 tag coverage 85-100%  (92%)
  [PASS] M4 chargeback gate is open  (True)
```

> Lưu ý: `Rubric.md` liệt kê 4 test cho `test_allocation.py`, nhưng file thật có 3 (`test_cost_by_tag`, `test_tag_coverage_and_gate`, `test_focus_rows`) — hai check coverage và gate được gộp vào một test. Tổng toàn repo vẫn đúng **15 tests**.

---

## Kết nối sang ticket tiếp theo

| Phát hiện M4 | Dùng ở đâu |
|---|---|
| Tổng phân bổ $8.47 khớp $8.48 của M2 | `M5-01` — kiểm tra nhất quán số liệu |
| 8.3% chi phí thiếu tag `project` | `DOC-01` — khuyến nghị: bắt buộc tag lúc tạo resource |
| `ResourceId` rỗng toàn bộ trong FOCUS export | `DOC-01` — lỗ hổng truy vết |
| `eval` batch 100% → $/1M thấp nhất dù reasoning 48% | `EXT-04` — reasoning bị batch che lấp |
| `search` + `assistant` batch 0% | `DOC-01` — hành động chi phí thấp |
| `search` có $/1M cao nhất (1.379) không rõ nguyên nhân | `DOC-01` — việc showback cần team tự điều tra |
