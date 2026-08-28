# Bài viết Lab 25, GPU FinOps

Nguyễn Xuân Quang, 2A202601776. Track 2, Day 25.

## 1. Baseline và optimized

Chạy `python missions/m5_report.py` thì ra baseline $27,133/tháng, optimized $14,626/tháng, tiết kiệm $12,507 tức 46%. Riêng phần inference thì `$/1M-token` giảm từ 6.488 xuống 1.126.

Nhưng em thấy con số 46% này hơi có vấn đề nên muốn nói luôn ở đây. Baseline trong code được tính bằng chi phí token của M2 cộng chi phí thuê GPU của M3:

```python
baseline = r2["baseline_daily"] * 30 + r3["on_demand_monthly"]
```

Trong khi đó hai lever cuối (right-size và kill idle) lại lấy dữ liệu từ `gpu_telemetry.csv`, tức 11 con GPU trị giá $15,394/tháng, mà đám GPU này không nằm trong baseline. Nói cách khác là em đang trừ tiền tiết kiệm ra khỏi một mẫu số không chứa thứ sinh ra khoản tiết kiệm đó. Nếu cộng cả fleet telemetry vào cho nhất quán thì baseline thành $42,527 và tỷ lệ tiết kiệm chỉ còn 29.4%. Chênh nhau 16.7 điểm phần trăm chỉ vì chọn mẫu số khác.

Em vẫn để nguyên code chứ không sửa, vì `workloads.csv` và `gpu_telemetry.csv` là hai lát cắt của cùng một hạ tầng nhìn từ hai góc khác nhau và lab không nối chúng bằng khóa chung. Nhưng em nghĩ báo cáo phải ghi rõ cả hai số, không thì người đọc sẽ hiểu 46% là tỷ lệ trên toàn bộ hóa đơn GPU.

## 2. Lever nào đóng góp nhiều nhất

| Lever | Tiết kiệm | Tỷ lệ |
|---|---|---|
| Purchasing (spot/reserved) | $10,040 | 80.3% |
| Inference (cascade/cache/batch) | $1,212 | 9.7% |
| Right-size util-lies | $655 | 5.2% |
| Kill idle GPUs | $600 | 4.8% |

Purchasing thắng áp đảo. Chỗ này làm em hơi bất ngờ, vì nếu nhìn theo phần trăm thì inference mới là cái ấn tượng: nó cắt 82.6%, còn purchasing chỉ cắt 39.1%. Nhưng mẫu số của inference chỉ có $1,466/tháng, còn purchasing là $25,667/tháng, chênh nhau 17.5 lần. Cắt 82.6% của một khoản nhỏ thì vẫn ra số nhỏ.

Em nghĩ bài học ở đây là khi ai đó khoe "giảm 82% chi phí LLM" thì câu hỏi đầu tiên phải là 82% của bao nhiêu.

Trong nội bộ M2 em có tách riêng ba đòn bẩy ra đo (mission chỉ in tổng gộp):

| Đòn bẩy | Bật một mình | Đóng góp biên |
|---|---|---|
| Cascade | tiết kiệm 76.5% | $27.64/ngày |
| Batch | 16.9% | $1.79/ngày |
| Cache | 9.4% | $1.17/ngày |

Cascade thắng ở cả hai cách đo. Lý do là chênh giá giữa model small và large là 15 lần ở input và 37.5 lần ở output, không đòn bẩy nào khác có hệ số cỡ đó. Batch tối đa 2 lần, cache tối đa 10 lần. Thêm nữa 79.4% traffic đi được tier small.

Cache yếu hơn em tưởng. Nghe "giảm 90%" thì tưởng ghê gớm nhưng thực tế chỉ đóng góp $1.17/ngày, vì cache chỉ áp lên input mà output mới là phần đắt, với lại cache hit thật chỉ 31.9% chứ không phải 100%. Cái `discount_stack` cho ra 0.05 là trần lý thuyết ở cache hit 100%, còn với dataset thật thì hệ số là 0.356.

Một chỗ nữa em muốn ghi lại: đọc waterfall theo thứ tự cộng dồn dễ đánh giá sai. Cache khi bật một mình tiết kiệm $4.60/ngày, nhưng nếu cascade chạy trước và kéo hóa đơn từ $48.87 xuống $11.48 rồi thì cache chỉ còn cắt được $1.20. Không phải vì cache kém đi mà vì phần bánh đã bị cột trước ăn mất.

## 3. GPU-Util lie

`gpu-h100-4` có GPU-Util 98.2%, cao nhất fleet, nhưng MFU chỉ 0.194, thấp nhất fleet.

May là dataset có sẵn nhóm đối chứng rất sạch để so. Bốn con `gpu-h100-0` đến `gpu-h100-3` cũng là H100, cũng chạy workload train, util 93 tới 95%, MFU từ 0.401 tới 0.427, trung bình 0.413. Tức là cùng phần cứng cùng loại việc, util nhích lên 4 điểm mà hiệu quả tính toán rớt hơn một nửa. Nếu `nvidia-smi` đo hiệu quả thật thì chuyện này không xảy ra được.

Lý do là hai chỉ số đếm hai thứ khác nhau. GPU-Util đếm phần trăm thời gian có ít nhất một kernel đang chạy, tức là GPU có bận hay không. MFU đếm FLOPs thực đạt trên FLOPs đỉnh, tức là GPU có làm được việc hay không. Một kernel dành phần lớn chu kỳ để chờ dữ liệu từ HBM vẫn được tính là đang hoạt động.

Chỗ này em thấy MBU giúp phân biệt nguyên nhân. `gpu-h100-4` có MFU 0.194 và MBU 0.207, cả hai đều thấp. Nếu MBU cao mà MFU thấp thì là nghẽn băng thông, chữa bằng cách đổi GPU hoặc gộp batch to hơn. Còn cả hai cùng thấp nghĩa là GPU không được cho đủ việc để làm, thường là do kernel launch overhead, batch size quá nhỏ, data loader chậm, hoặc chờ all-reduce từ rank chậm nhất. Em không chắc chắn là cái nào trong bốn cái đó vì dữ liệu telemetry không có thông tin để phân biệt tiếp, muốn biết chắc thì phải profile bằng nsys.

Có một chi tiết nữa em thấy đáng ghi: `power_w` của con này là 693.5W, cao nhất fleet và sát trần 700W. Nó ăn điện nhiều nhất trong khi sinh ra ít FLOPs nhất. Clock chạy hết công suất, tiền điện vẫn tốn, việc hữu ích thì không có.

Về tác động tài chính, em lấy MFU của nhóm H100 khỏe mạnh (0.413) làm chuẩn:

| GPU | Chi phí/ngày | MFU | Tiền trả cho FLOPs không nhận được |
|---|---|---|---|
| gpu-h100-4 | $60.00 | 0.194 | $31.80/ngày, tức $954/tháng |
| gpu-a10g-1 | $24.00 | 0.268 | $5.64/ngày, tức $169/tháng |

Cộng thêm idle waste $600/tháng của `gpu-h100-5` thì tổng là $1,723/tháng, chiếm 11.2% chi phí fleet ($15,394/tháng). Toàn bộ khoản này không cần mua thêm GPU nào để lấy lại, mà nó lại vô hình trên dashboard vì `gpu-h100-4` hiển thị 98% util, con số đẹp nhất fleet.

Về phần idle thì em suýt bỏ sót. Nếu chỉ nhìn util trung bình ngày thì không GPU nào dưới 10%, `gpu-h100-5` trung bình 61% trông hoàn toàn bình thường. Phải zoom xuống từng giờ mới thấy nó nằm không 8/24 giờ. Đây chắc là lý do `idle_waste_usd()` nhận tham số `idle_hours` chứ không nhận `avg_util`.

## 4. Hai extension em làm

### EXT-01, viết lại `recommend_tier()`

Đọc code M3 em tìm được ba lỗi:

Thứ nhất, nó bỏ qua cột `days` hoàn toàn, dùng `DAYS = 30` cho cả 8 job kể cả job chỉ chạy 3 ngày. Chi phí `job-finetune` bị thổi lên 10 lần và baseline on-demand từ $16,539 thành $25,667.

Thứ hai, nó hardcode `reserved_discount=0.45`. Chiết khấu thật trong catalog dao động từ 37.1% tới 44.1% nên break-even thật là 55.9% tới 62.9% tùy GPU. Với B200 phải chạy 15.1 giờ/ngày mới hòa vốn chứ không phải 13.2.

Thứ ba, nó tính chi phí reserved bằng `gpu_hours * reserved_3yr_hr`, tức chỉ trả cho giờ job chạy. Nhưng reservation bill 24 giờ/ngày dù dùng hay không. Với `job-infer-search` duty 75% thì v1 tính $972 trong khi thật ra là $1,296, thiếu 25%.

Policy mới của em thêm interruption rate theo từng loại GPU (lấy từ chính mức chiết khấu spot trong catalog, vì thị trường đã định giá rủi ro thu hồi vào đó, A10G giảm 60% và L4 giảm 56% cũng chính là hai GPU bị thu hồi nhiều nhất), cho reserved 1yr và 3yr cạnh tranh nhau, đọc break-even từ catalog, và quan trọng nhất là chỉ cho ký cam kết xa bằng tầm nhìn nhu cầu:

```python
commitment_utilization = duty × min(1, demand_days / term_days)
```

Kết quả đo trên cùng horizon days-aware:

| | Tổng $/tháng | Tiết kiệm |
|---|---|---|
| on-demand | 16,539 | |
| v1 policy | 9,849 | 40.5% |
| v2 policy | 12,302 | 25.6% |

Tức là policy mới của em đắt hơn policy cũ $2,453/tháng. Lúc đầu em tưởng mình làm sai ở đâu đó, nhưng nghĩ kỹ thì đây là kết quả đúng. Khoản tiết kiệm 40.5% của v1 một phần là hư cấu, vì nó ký reserved 3 năm cho workload mới có 30 ngày bằng chứng. Nếu sản phẩm đổi hướng sau 8 tháng thì còn 28 tháng hợp đồng phải trả. Với lại nó tính thiếu 25% ở chỗ bill 24/7 như nói trên, sửa riêng lỗi đó thì v1 thật ra tốn $10,173.

Em có chạy thêm độ nhạy theo tầm nhìn nhu cầu để kiểm tra xem policy có phản ứng đúng không:

| Tầm nhìn | Tổng $/tháng | Tier chọn |
|---|---|---|
| 180 ngày | 14,009 (15.3%) | 5 spot, 3 on-demand |
| 365 ngày | 12,302 (25.6%) | 5 spot, 2 rsv-1yr, 1 on-demand |
| 730 ngày | 10,574 (36.1%) | 5 spot, 2 rsv-3yr, 1 on-demand |
| 1095 ngày | 10,142 (38.7%) | 5 spot, 3 rsv-3yr |

Đọc bảng này em thấy khá thú vị: đi từ 6 tháng lên 3 năm tầm nhìn đáng giá $3,867/tháng. Nghĩa là thông tin roadmap sản phẩm có giá cụ thể bằng tiền, chứ không phải chuyện chỉ liên quan tới team product.

### EXT-02, right-sizing theo MBU

Em thêm hàm `unit_prices()` tính `$/GB-VRAM-hr` và `$/(TB/s)-hr` bên cạnh `$/GPU-hr`. Hai bảng xếp hạng đảo ngược nhau:

| GPU | $/hr | $/GB-hr | $/TBs-hr |
|---|---|---|---|
| MI300X | 1.95 | 0.0102 | 0.368 |
| A100 | 1.79 | 0.0224 | 0.895 |
| B200 | 5.09 | 0.0265 | 0.636 |
| H100 | 2.50 | 0.0312 | 0.746 |
| L4 | 0.80 | 0.0333 | 2.667 |
| A10G | 1.00 | 0.0417 | 1.667 |

L4 rẻ nhất theo giờ nhưng xếp áp chót về $/GB và chót về $/(TB/s), đắt hơn MI300X 7.2 lần trên mỗi đơn vị băng thông. Ngược lại B200 đắt nhất bảng lại rẻ thứ ba theo $/GB. Với workload decode là memory-bound (arithmetic intensity chỉ 1 tới 2 FLOP/byte, dưới ridge point 295 của H100 rất xa) thì băng thông mới là thứ sinh ra token, nên mua L4 vì nó rẻ theo giờ thì trả nhiều tiền hơn cho mỗi token.

Hàm `rightsize_by_mbu()` của em chọn GPU thay thế theo những gì thiết bị thực sự tiêu thụ, với headroom 25%, và chỉ đụng vào GPU thực sự thừa công suất (MFU dưới 0.35 và MBU dưới 0.60). Kết quả tìm được $792/tháng, so với $655 của lever right-size trong M5. M5 dùng bảng hạ cấp cứng H100 sang A100 nên không kiểm tra GPU thay thế có đủ VRAM không, và bỏ sót `gpu-h100-5` vì con này util 61% nên không bị gắn cờ lie.

Chỗ này em gặp một cái ngoài dự kiến. Lúc viết test kiểm tra ràng buộc headroom thì cả 11/11 GPU đều trượt, mà không phải vì băng thông, là vì bộ nhớ:

| GPU | Peak VRAM dùng | Dung lượng | Còn dư |
|---|---|---|---|
| gpu-h100-0/1/3 | 67.5 GB | 80 GB | 18.5% |
| gpu-a100-0 | 67.7 GB | 80 GB | 18.2% |
| gpu-a10g-1 | 20.4 GB | 24 GB | 17.6% |

Cả fleet chạy ở mức 80 tới 82% VRAM, trong khi MFU chỉ 0.19 tới 0.43 và MBU 0.21 tới 0.45. Fleet cạn bộ nhớ trước khi cạn sức tính toán. Điều này giải thích luôn tại sao 5 con GPU không tìm được phương án rẻ hơn: không phải vì giá, mà vì không GPU rẻ hơn nào đủ VRAM. Em nghĩ hướng đúng cho NimbusAI không phải là mua GPU rẻ hơn mà là giảm nhu cầu VRAM trước (quantization, KV-cache paging, tensor parallel), làm được thì cả 11 con mới mở ra lựa chọn rẻ hơn.

Cả hai extension em viết thêm 12 test trong `tests/test_ext_policies.py` và không sửa file test cũ. Policy mặc định của M3 vẫn là v1 nên `verify.py` vẫn 11/11.

## 5. Ba việc em sẽ làm đầu tiên nếu là FinOps lead

Việc 1, tắt `gpu-h100-5` trong 8 giờ idle, và bắt buộc tag `project` lúc tạo resource.

Cái đầu được $600/tháng với công sức gần bằng không và rủi ro bằng không, chỉ là chuyện scheduling. Trong waterfall nó xếp chót về tiền nên nếu chỉ đọc biểu đồ thì sẽ làm nó cuối cùng, nhưng em nghĩ waterfall xếp theo tiền chứ không xếp theo độ dễ.

Cái thứ hai không ra tiền ngay nhưng mở đường. Tag coverage đang 91.8%, nghe thì ổn nhưng toàn bộ phần thiếu nằm ở `project` chứ không phải `team` (197/2400 dòng thiếu project, 0 dòng thiếu team). Nghĩa là showback theo team thì chính xác 100% và gửi được ngay hôm nay, còn chargeback theo project thì chưa, vì 8.3% chi phí rơi vào untagged, đủ để một PM phản đối con số dự án mình. Với lại coverage 91.8% chỉ qua được ngưỡng 80% và 90%, trượt ngay khi nâng chuẩn lên 95%. Còn một lỗ nữa là cột `ResourceId` trong FOCUS export rỗng toàn bộ, nên biết team nào tiêu tiền mà không truy ngược được về endpoint nào.

Việc 2, chuyển 5 job interruptible sang spot, và bật batch cho traffic offline.

Spot cho 5 job được khoảng $5,700/tháng. Nhưng phải nói rõ với team là giá spot thật không phải giá trên bảng giá: `job-train-llm` cần 2,240 GPU-giờ mà phải trả 2,363.2 giờ, gồm 67.2 giờ overhead ghi checkpoint và 56 giờ chạy lại sau khi bị thu hồi. Giá hiệu dụng là $1.58/giờ chứ không phải $1.50, nên tiết kiệm thật 36.7% chứ không phải 40% ghi trên catalog. Không có checkpoint thì spot không phải chiến lược tiết kiệm mà là canh bạc.

Về batch thì hiện `is_batch=1` mới chiếm 17.3% traffic. Team `eval` đã batch 100% và nhờ đó có `$/1M-token` là 0.983, gần thấp nhất, dù tỷ lệ reasoning của họ cao nhất (48.4%). Còn `search` và `assistant` batch 0%. Em không nghĩ toàn bộ traffic của hai team đó batch được, nhưng con số 0% nghĩa là chưa ai thử tách phần không cần realtime ra.

Việc 3, chưa ký reserved 3 năm cho tới khi có roadmap ít nhất 2 năm.

Đây là kết luận từ EXT-01. Ba job infer đang chạy duty 75 tới 100% nên nhìn qua thì rất đáng ký 3 năm, nhưng bằng chứng chỉ có 30 ngày. Em sẽ ký 1 năm trước, chấp nhận hóa đơn cao hơn khoảng $2,453/tháng so với phương án 3 năm, rồi nếu sau 12 tháng nhu cầu vẫn còn thì mới chuyển sang term dài. Bảng độ nhạy ở trên cho thấy đúng con số phải trả cho việc không chắc chắn.

Còn một việc nữa em xếp ngoài top 3 nhưng muốn ghi lại vì nó rẻ. `report.md` in "Cheapest+cleanest region: europe-north1", nhưng đọc code thì hàm chọn vùng chỉ lấy `min(REGION_CARBON)`, hoàn toàn không nhìn `REGION_PRICE_KWH`. `europe-north1` sạch nhất thật (30 gCO2/kWh) nhưng `us-east-wa` rẻ hơn 39% ($0.055 so với $0.090) và carbon xếp hạng nhì (90 gCO2/kWh). Chuyển job interruptible sang `us-east-wa` thì tiền điện giảm 54% và carbon giảm 76%.

Tiền điện ở đây chỉ khoảng $114/tháng nên không đáng kể so với hóa đơn GPU, vì trong mô hình thuê cloud thì tiền điện đã nằm trong giá thuê rồi. Nhưng phần carbon thì đáng: 361.1 kgCO2/tháng ở `us-east-1` xuống 28.5 kg ở `europe-north1`. Và con số làm em ngạc nhiên nhất cả lab nằm ở đây: request reasoning chiếm 8.4% traffic nhưng 94% tổng năng lượng. Bỏ hết reasoning thì năng lượng từ 31,675 Wh/ngày xuống 2,260 Wh/ngày, giảm 14 lần. Nếu có thời gian làm tiếp EXT-04 thì em nghĩ routing rule cho reasoning là chỗ đáng làm nhất về mặt năng lượng.

## Kết quả kiểm tra

```
python verify.py   ->  11/11 checks passed
pytest -q          ->  27 passed (15 test gốc + 12 test em viết cho hai extension)
```

File nộp: `outputs/report.md`, `outputs/savings.png`, `outputs/focus_export.csv`, và bài viết này.
