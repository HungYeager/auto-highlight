# Quy tắc Tự động Kích hoạt Kỹ năng (Smart Skills Assistant Rule)

Người dùng KHÔNG CẦN phải nhớ tên kỹ năng (skills) hay câu lệnh kỹ thuật. 
Trách nhiệm của AI Assistant là **tự động lắng nghe ngữ cảnh ngôn ngữ tự nhiên** của người dùng và chọn vũ khí/kỹ năng phù hợp nhất để hỗ trợ.

---

### Bản đồ ánh xạ tự động theo tình huống (Intent Mapping):

1. **Khi người dùng báo lỗi, crash, đơ, giật lag hoặc chạy chậm:**
   - **Tự động áp dụng:** `diagnosing-bugs`
   - **Hành động:** Tạo feedback loop (kiểm chứng bằng lệnh/script cụ thể), cô lập nguyên nhân gốc rễ (root cause) trước khi sửa, tuyệt đối không đoán mò hay sửa hú họa.

2. **Khi người dùng có ý tưởng mới hoặc yêu cầu còn chung chung, mơ hồ:**
   - **Tự động áp dụng:** `grill-me` & `prototype`
   - **Hành động:** Đặt từ 2 - 3 câu hỏi trọng tâm, ngắn gọn về kiến trúc/trải nghiệm người dùng để chốt phương án trước khi gõ code, tránh làm thừa hoặc làm sai ý.

3. **Khi người dùng yêu cầu viết tính năng quan trọng, đòi hỏi độ chính xác cao:**
   - **Tự động áp dụng:** `tdd` (Test-Driven Development) & `codebase-design`
   - **Hành động:** Viết kịch bản kiểm thử (test/verification) trước, sau đó viết code để pass test và refactor sạch sẽ.

4. **Khi người dùng yêu cầu "kiểm tra lại", "review code", "xem có lỗi bảo mật/rò rỉ không":**
   - **Tự động áp dụng:** `open-code-review` (Chuẩn Alibaba) & `open-code-review-delegate`
   - **Hành động:** Quét theo bộ tiêu chuẩn bảo mật, chống race condition, quản lý tài nguyên và line-level precision.

5. **Khi người dùng muốn hiểu cách hoạt động hoặc học công nghệ mới:**
   - **Tự động áp dụng:** `teach`
   - **Hành động:** Giải thích trực quan, chia nhỏ khái niệm, dùng ví dụ thực tế trong chính dự án thay vì lý thuyết suông.

6. **Khi code phình to, lộn xộn, khó bảo trì:**
   - **Tự động áp dụng:** `improve-codebase-architecture`
   - **Hành động:** Đề xuất tái cấu trúc theo mô hình module sâu (Deep Modules), tách biệt logic và giao diện.
