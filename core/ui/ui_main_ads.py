import random
from datetime import datetime

def _get_product_context(recommended_name):
    """Phân loại sản phẩm thông minh để lấy đơn vị, hành động và tính từ"""
    lower_name = recommended_name.lower()
    
    # Nhóm đồ uống
    if any(kw in lower_name for kw in ['nước', 'trà', 'cà phê', 'coffee', 'coca', 'pepsi', 'sting', 'bò húc', 'sữa', 'aquafina']):
        don_vi = random.choice(["lon", "chai"])
        hanh_dong = random.choice(["giải khát", "uống", "làm ngụm"])
        tinh_tu = random.choice(["mát lạnh", "sảng khoái"])
        
    # Nhóm đồ ăn vặt / Snack
    elif any(kw in lower_name for kw in ['bánh', 'kẹo', 'oreo', 'chocopie', 'socola', 'kẹo mút']):
        don_vi = random.choice(["gói", "hộp", "chiếc", "thanh"])
        hanh_dong = random.choice(["nhâm nhi", "lót dạ", "nếm thử"])
        tinh_tu = random.choice(["ngọt ngào", "thơm ngon", "hấp dẫn", "tan chảy"])
        
    # Fallback
    else:
        don_vi = "phần"
        hanh_dong = "thưởng thức"
        tinh_tu = "tuyệt vời"
        
    return don_vi, hanh_dong, tinh_tu

def generate_recommendation_messages(user_name, recommended_name):
    """Trả về câu chào và câu gợi ý dựa theo khung giờ thực tế"""
    don_vi, hanh_dong, tinh_tu = _get_product_context(recommended_name)
    hour = datetime.now().hour
    
    # --- LOGIC CÁ NHÂN HÓA LỜI CHÀO THEO THỜI GIAN ---
    if 0 <= hour < 3:
        greetings = [
            f"Giờ này mà {user_name} vẫn còn thức cày deadline sao? 🦉",
            f"Đêm khuya thanh vắng, nạp chút đồ để {hanh_dong} cho đỡ buồn ngủ nhé.",
            f"Máy vẫn luôn thức cùng {user_name} đây. Cần gì cứ chốt đơn nha!",
            f"Thức khuya hại sức khỏe lắm, nạp năng lượng rồi nghỉ ngơi sớm {user_name} nhé."
        ]
    elif 3 <= hour < 5:
        greetings = [
            f"Trời sắp sáng rồi đó {user_name} ơi! 🌌",
            f"Thức trắng đêm rồi sao? Bổ sung năng lượng gấp nào!",
            f"Sương còn chưa tan mà {user_name} đã ghé máy rồi.",
            f"Cố lên {user_name}, sắp qua ngày mới rồi!"
        ]
    elif 5 <= hour < 7:
        greetings = [
            f"Bình minh lên rồi! Chào buổi sáng sớm {user_name}. 🌅",
            f"Dậy sớm thế {user_name}! Khởi động ngày mới thôi.",
            f"Tập thể dục xong rồi thì làm một {don_vi} sảng khoái nhé?",
            f"Không khí buổi sáng thật trong lành, chúc {user_name} một ngày tốt lành!"
        ]
    elif 7 <= hour < 9:
        greetings = [
            f"Bắt đầu ca làm/học rồi, {user_name} đã dùng bữa sáng chưa? 🥐",
            f"Giờ cao điểm tất bật quá, đừng quên nạp năng lượng nha {user_name}.",
            f"Chào buổi sáng rực rỡ! Khởi đầu ngày mới thật bùng nổ nhé {user_name}!",
            f"Đừng để bụng đói bắt đầu công việc nhé {user_name}."
        ]
    elif 9 <= hour < 11:
        greetings = [
            f"Nghỉ giải lao giữa buổi một chút nhé {user_name}!",
            f"Làm việc từ sáng căng thẳng rồi, kiếm gì {hanh_dong} thôi.",
            f"Nạp thêm chút đường để não bộ hoạt động hết công suất nào {user_name} ơi.",
            f"Còn một chút nữa là đến trưa rồi, duy trì phong độ nhé {user_name}."
        ]
    elif 11 <= hour < 12:
        greetings = [
            f"Sắp nghỉ trưa rồi, ráng lên {user_name} ơi! ⏳",
            f"Bụng bắt đầu réo rồi đúng không {user_name}?",
            f"Chuẩn bị gác lại công việc, tìm món gì đó thưởng thức thôi.",
            f"Chút xíu nữa là được nghỉ trưa rồi {user_name} nhé."
        ]
    elif 12 <= hour < 13:
        greetings = [
            f"Giờ vàng nghỉ ngơi đây rồi! Chúc {user_name} buổi trưa vui vẻ. 🍱",
            f"Ăn trưa xong làm một {don_vi} tráng miệng là chuẩn bài nhé {user_name}.",
            f"Tranh thủ chợp mắt một chút cho buổi chiều bùng nổ nha {user_name}.",
            f"Nghỉ tay thôi {user_name}, hệ thống phục vụ bạn ngay đây."
        ]
    elif 13 <= hour < 14:
        greetings = [
            f"Chuẩn bị vào ca chiều, xốc lại tinh thần nào {user_name}! ☕",
            f"Đầu giờ chiều dễ buồn ngủ lắm, kiếm gì {hanh_dong} cho tỉnh táo nhé.",
            f"Vực lại năng lượng, sẵn sàng chiến đấu tiếp thôi {user_name} ơi.",
            f"Hy vọng {user_name} đã có một giờ nghỉ trưa trọn vẹn!"
        ]
    elif 14 <= hour < 16:
        greetings = [
            f"Giờ làm việc căng thẳng nhất đây, ráng lên {user_name}! 💪",
            f"Tạm gác công việc lại vài phút, {hanh_dong} chút gì cho đỡ stress nhé.",
            f"Hệ thống thấy bạn làm việc chăm chỉ quá, tự thưởng cho mình đi {user_name}.",
            f"Buồn ngủ chưa {user_name}? Để máy bán hàng lo!"
        ]
    elif 16 <= hour < 18:
        greetings = [
            f"Sắp tan tầm rồi! Cố gắng chút nữa thôi {user_name}. 🌇",
            f"Năng lượng cạn kiệt cuối ngày rồi, sạc lại gấp nào.",
            f"Hoàn thành nốt công việc rồi chuẩn bị về nhà thôi {user_name}.",
            f"Chút xíu nữa là được nghỉ rồi, {user_name} giữ phong độ nhé."
        ]
    elif 18 <= hour < 19:
        greetings = [
            f"Hoàng hôn buông rồi, vừa tan ca đúng không {user_name}? 🌆",
            f"Một ngày dài đã qua, xả stress với món đồ yêu thích nhé {user_name}!",
            f"Trời vừa sập tối, {user_name} nhớ lót dạ gì đó nha.",
            f"Chào buổi tối! {user_name} ghé máy là chuẩn bài luôn."
        ]
    elif 19 <= hour < 21:
        greetings = [
            f"Buổi tối thảnh thơi nhé, {user_name}! 🌃",
            f"Tối nay {user_name} định {hanh_dong} gì nào?",
            f"Không gian chill thế này, làm một {don_vi} là hết ý {user_name} ơi!",
            f"Thư giãn buổi tối thôi {user_name}!"
        ]
    elif 21 <= hour < 22:
        greetings = [
            f"Tối muộn rồi, {user_name} giải lao chút trước khi nghỉ ngơi nhé! 🌙",
            f"Sắp hết ngày rồi, chốt lại bằng món đồ yêu thích nhé {user_name}.",
            f"Muộn thế này mà {user_name} vẫn chăm chỉ ghê!",
            f"Ngày mai lại là một ngày mới, nạp năng lượng thư giãn đi {user_name}."
        ]
    else: # 22:00 - 23:59
        greetings = [
            f"Khuya rồi, {user_name} vẫn đang chiến đấu à? 🌌",
            f"Thời gian tĩnh lặng nhất trong ngày, để máy đồng hành cùng {user_name} nhé.",
            f"Thức khuya dễ đói, {hanh_dong} chút gì đi {user_name}!",
            f"Chạy deadline hay làm đồ án thế {user_name}? Cố lên nhé!"
        ]
        
    suggest_texts = [
        f"Hệ thống thấy bạn rất chuộng '{recommended_name}'. Làm ngay một {don_vi} để {hanh_dong} nhé?",
        f"Món 'ruột' của bạn đây rồi! Quất luôn một {don_vi} '{recommended_name}' {tinh_tu} không?",
        f"Đã lâu không gặp, bạn có muốn {hanh_dong} lại '{recommended_name}' quen thuộc không?",
        f"Máy vừa lên kệ '{recommended_name}' dành riêng cho bạn. Thêm 1 {don_vi} vào giỏ chứ?",
        f"Trông có vẻ bạn đang cần một {don_vi} '{recommended_name}'. Bấm nút chốt đơn luôn nhé?",
        f"Đừng quên tự thưởng cho mình một {don_vi} '{recommended_name}' {tinh_tu} nha!",
        f"Nghĩ đến '{recommended_name}' là thấy hợp lý rồi. Thêm ngay 1 {don_vi} vào giỏ hàng thôi!",
        f"Gương mặt thân quen lại chọn '{recommended_name}' đúng không? Lấy ngay 1 {don_vi} nào!",
        f"Hệ thống đoán là bạn đang muốn {hanh_dong} '{recommended_name}'. Chọn luôn cho nóng nhé!",
        f"Chỉ thiếu một {don_vi} '{recommended_name}' {tinh_tu} nữa là hoàn hảo. Bạn có muốn lấy không?",
        f"Cơ sở dữ liệu báo rằng bạn rất thích '{recommended_name}'! Ủng hộ máy 1 {don_vi} nhé?",
        f"Chưa biết chọn gì thì cứ '{recommended_name}' mà tiến thôi. Bấm mua ngay nào!"
    ]

    return random.choice(greetings), random.choice(suggest_texts)