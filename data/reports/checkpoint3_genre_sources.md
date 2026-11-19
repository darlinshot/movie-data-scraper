# Checkpoint 3 genre backfill sources

`data/filtered/checkpoint3.csv` had 10 rows with an empty `genre` field. The
filled values use only labels already present in the other 69 rows. No new
genre label (for example `Hoạt hình`) was introduced.

| Movie | Filled genre | Evidence |
|---|---|---|
| Doraemon Movie 45 (2026): Nobita Và Lâu Đài Dưới Đáy Biển | Khoa học viễn tưởng, Phiêu lưu, Gia đình | Wikipedia describes an animated science-fantasy film; categories include `Japanese animated science fiction films` and `2026 children's animated films`. https://en.wikipedia.org/wiki/Doraemon%3A_New_Nobita_and_the_Castle_of_the_Undersea_Devil |
| Doraemon 2025: Nobita Và Cuộc Phiêu Lưu Vào Thế Giới Trong Tranh | Khoa học viễn tưởng, Phiêu lưu, Gia đình | Wikipedia: “animated science fantasy adventure film”; categories include science fiction and children's animated films. https://en.wikipedia.org/wiki/Doraemon%3A_Nobita%27s_Art_World_Tales |
| Phim Điện Ảnh Doraemon: Nobita Và Bản Giao Hưởng Địa Cầu | Khoa học viễn tưởng, Phiêu lưu, Âm nhạc, Gia đình | Wikipedia: “animated musical science fantasy adventure film”. https://en.wikipedia.org/wiki/Doraemon%3A_Nobita%27s_Earth_Symphony |
| Doraemon: Nobita Và Vùng Đất Lý Tưởng Trên Bầu Trời | Khoa học viễn tưởng, Phiêu lưu, Gia đình | Wikipedia: “animated science fiction adventure film”. https://en.wikipedia.org/wiki/Doraemon%3A_Nobita%27s_Sky_Utopia |
| Doraemon: Nobita Và Cuộc Chiến Vũ Trụ Tí Hon 2021 | Khoa học viễn tưởng, Phiêu lưu, Gia đình | Wikipedia: “animated epic space opera film”; categories include science fiction and children's animated films. https://en.wikipedia.org/wiki/Doraemon%3A_Nobita%27s_Little_Star_Wars_2021 |
| Doraemon: Luôn Bên Bạn | Khoa học viễn tưởng, Hài, Gia đình | Wikipedia: “animated science fiction comedy film”; categories include children's animated films. https://en.wikipedia.org/wiki/Stand_by_Me_Doraemon_2 |
| Doraemon: Nobita và Mặt Trăng Phiêu Lưu Ký | Khoa học viễn tưởng, Phiêu lưu, Gia đình | Wikipedia: “anime epic science fiction film”; categories include `2019 adventure films` and children's animated films. https://en.wikipedia.org/wiki/Doraemon%3A_Nobita%27s_Chronicle_of_the_Moon_Exploration |
| Conan Movie 28: Dư Ảnh Của Độc Nhãn | Bí ẩn, Trinh thám, Tội phạm | Wikipedia: “animated mystery film”; categories include `Anime mystery films`. The crime label follows the robbery case in the film synopsis. https://en.wikipedia.org/wiki/Detective_Conan%3A_One-eyed_Flashback |
| Thanh Gươm Diệt Quỷ: Vô Hạn Thành | Hành động, Tâm linh | Wikipedia: “animated dark fantasy film”; categories include action films and films about demons. No new `Fantasy` or `Horror` label was introduced. https://en.wikipedia.org/wiki/Demon_Slayer%3A_Kimetsu_no_Yaiba_%E2%80%93_The_Movie%3A_Infinity_Castle |
| Phim Điện Ảnh Conan 27: Ngôi Sao 5 Cánh 1 Triệu Đô | Bí ẩn, Trinh thám, Tội phạm | Wikipedia: “animated mystery film”. The crime label follows the phantom-thief/heist plot in the synopsis. https://en.wikipedia.org/wiki/Detective_Conan%3A_The_Million-dollar_Pentagram |

Validation: every comma-separated token assigned above is one of the 28 genre
labels already used by checkpoint 3 before the backfill.
