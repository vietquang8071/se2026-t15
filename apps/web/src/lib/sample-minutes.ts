export type SampleMinutes = {
  summary: string;
  actionItems: { task: string; owner: string; due: string }[];
  decisions: string[];
  openIssues: string[];
  followUps: string[];
  timeline: { date: string; event: string }[];
  transcript: { time: string; speaker: string; text: string }[];
};

export const SAMPLE_MINUTES: SampleMinutes = {
  summary:
    "Nhóm thống nhất ưu tiên hoàn thiện luồng tạo cuộc họp và tải audio trước khi mở rộng các tính năng AI. Bản MVP cần giúp người dùng kiểm tra transcript, xác nhận các đầu việc và xuất biên bản theo cấu trúc rõ ràng.",
  actionItems: [
    {
      task: "Hoàn thiện hợp đồng API cho luồng tạo meeting",
      owner: "Minh Anh",
      due: "28/10/2026",
    },
    {
      task: "Chuẩn bị bộ audio mẫu cho kiểm thử",
      owner: "Quang Huy",
      due: "30/10/2026",
    },
    {
      task: "Rà soát nội dung sáu phần của biên bản",
      owner: "Lan Phương",
      due: "02/11/2026",
    },
  ],
  decisions: [
    "Bản đầu tiên nhận audio có sẵn qua tải file; chưa hỗ trợ ghi âm trực tiếp trong ứng dụng.",
    "Biên bản gồm sáu phần: tóm tắt, công việc, quyết định, vấn đề mở, theo dõi và dòng thời gian.",
  ],
  openIssues: [
    "Cần thống nhất cách hiển thị speaker chưa xác định trong transcript.",
    "Chưa chốt thời điểm cho phép chỉnh sửa nội dung đã được AI trích xuất.",
  ],
  followUps: [
    "Đánh giá chất lượng transcript trên audio tiếng Việt có nhiều người nói.",
    "Xác nhận định dạng export được ưu tiên sau Markdown.",
  ],
  timeline: [
    { date: "27/10/2026", event: "Chốt hợp đồng API và schema biên bản" },
    { date: "30/10/2026", event: "Hoàn tất bộ audio mẫu cho kiểm thử" },
    { date: "04/11/2026", event: "Demo luồng tạo meeting và xem kết quả" },
  ],
  transcript: [
    {
      time: "00:02",
      speaker: "Minh Anh",
      text: "Mình nên chốt luồng tải file và ngày họp trước, rồi mới đưa thêm phần phân tích.",
    },
    {
      time: "00:18",
      speaker: "Quang Huy",
      text: "Đồng ý. Với bản đầu tiên, nhóm sẽ dùng các file audio đã có sẵn.",
    },
    {
      time: "00:34",
      speaker: "Lan Phương",
      text: "Mình sẽ rà lại sáu phần của biên bản để tên gọi và nội dung nhất quán.",
    },
    {
      time: "00:51",
      speaker: "Minh Anh",
      text: "Phần công việc cần có người phụ trách và ngày đến hạn nếu cuộc họp đã nêu rõ.",
    },
    {
      time: "01:09",
      speaker: "Quang Huy",
      text: "Với các mốc thời gian tương đối, mình sẽ dựa trên ngày họp để hiển thị ngày cụ thể.",
    },
    {
      time: "01:28",
      speaker: "Lan Phương",
      text: "Các câu hỏi chưa giải quyết nên tách riêng khỏi phần việc cần theo dõi sau cuộc họp.",
    },
    {
      time: "01:46",
      speaker: "Minh Anh",
      text: "Đúng rồi, phần quyết định cũng cần ghi rõ điều nhóm đã thống nhất.",
    },
    {
      time: "02:03",
      speaker: "Quang Huy",
      text: "Mình sẽ chuẩn bị audio mẫu và ghi lại các trường hợp transcript có nhiều người nói.",
    },
    {
      time: "02:24",
      speaker: "Minh Anh",
      text: "API tạo cuộc họp cần nhận tiêu đề, ngày họp và danh sách người tham gia trước khi nhận file audio.",
    },
    {
      time: "02:47",
      speaker: "Quang Huy",
      text: "Phần tải file nên hỗ trợ audio tối đa một trăm megabyte và báo rõ định dạng được chấp nhận.",
    },
    {
      time: "03:11",
      speaker: "Lan Phương",
      text: "Phía máy chủ vẫn cần tự kiểm tra MIME, dung lượng và file rỗng, không chỉ dựa vào kiểm tra trên giao diện.",
    },
    {
      time: "03:34",
      speaker: "Minh Anh",
      text: "Trong bản giao diện đầu tiên, cần nói rõ file mới chỉ được chọn trên trình duyệt và chưa được xử lý.",
    },
    {
      time: "03:58",
      speaker: "Quang Huy",
      text: "Trang kết quả vẫn nên giữ sáu phần riêng để người dùng tìm nhanh đúng nội dung cần xem.",
    },
    {
      time: "04:22",
      speaker: "Lan Phương",
      text: "Mỗi đầu việc cần có người phụ trách và hạn chót khi cuộc họp nêu đủ thông tin, còn thiếu thì để trống.",
    },
    {
      time: "04:46",
      speaker: "Minh Anh",
      text: "Ngày tương đối phải tính theo ngày diễn ra cuộc họp; câu chưa đủ rõ thì đánh dấu để xem lại.",
    },
    {
      time: "05:10",
      speaker: "Quang Huy",
      text: "Transcript cần giữ mốc thời gian để sau này có thể phát lại audio từ đúng đoạn được nhắc tới.",
    },
    {
      time: "05:34",
      speaker: "Lan Phương",
      text: "Nếu phần tóm tắt hoặc quyết định có thể dẫn về câu nói nguồn thì người dùng sẽ dễ kiểm tra hơn.",
    },
    {
      time: "05:58",
      speaker: "Minh Anh",
      text: "Tên người nói do hệ thống nhận diện cũng cần cho phép sửa lại khi hai giọng gần giống nhau.",
    },
    {
      time: "06:23",
      speaker: "Quang Huy",
      text: "Nút tải toàn bộ sau này sẽ đóng gói đủ sáu loại biên bản thay vì chỉ xuất một file tóm tắt.",
    },
    {
      time: "06:47",
      speaker: "Lan Phương",
      text: "Các nút tải trên từng thẻ có thể để trạng thái sắp có cho tới khi định dạng xuất được chốt.",
    },
    {
      time: "07:12",
      speaker: "Minh Anh",
      text: "Khi API sẵn sàng, nhóm sẽ thay dữ liệu minh họa bằng kết quả thật và kiểm tra lại trạng thái tải file.",
    },
    {
      time: "07:36",
      speaker: "Quang Huy",
      text: "Kiểm thử giao diện dùng dữ liệu giả cần được ghi riêng để không nhầm với kết quả từ provider thật.",
    },
    {
      time: "07:58",
      speaker: "Lan Phương",
      text: "Hai giao diện sáng và tối đều cần giữ độ tương phản tốt cho nội dung dài và nhãn phụ.",
    },
    {
      time: "08:21",
      speaker: "Minh Anh",
      text: "Trên màn hình lớn, hai cột nên dùng hết chiều cao khả dụng để không phải cuộn cả trang.",
    },
    {
      time: "08:43",
      speaker: "Quang Huy",
      text: "Danh sách biên bản và các dòng transcript có thể cuộn riêng, còn tiêu đề từng vùng luôn cần nhìn thấy.",
    },
    {
      time: "09:06",
      speaker: "Lan Phương",
      text: "Trên điện thoại thì chuyển về một cột và để trang cuộn tự nhiên sẽ dễ thao tác hơn.",
    },
    {
      time: "09:28",
      speaker: "Minh Anh",
      text: "Trước buổi demo, mình sẽ rà lại nội dung mẫu, các trạng thái lỗi và cách hiển thị khi chưa có người tham gia.",
    },
  ],
};
