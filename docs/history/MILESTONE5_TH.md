> Historical development note. For current commands and verification scope, start with [README](../../README.md). Counts and pending items below describe that stage.

# Milestone 5 — Dashboard และความเข้าใจ

ใช้คำสั่งเหมือนเดิม:

```bash
cd "/Users/sierra6/Documents/logistics-operations-analytics"
python3 project.py
python3 verify_release.py
open output/dashboard.html
open docs/guides/PRESENTATION_GUIDE_TH.md
```

หน้าตาใหม่: สี navy/teal, KPI cards, แท็บ 4 ส่วน, กราฟ OTIF ตามคลัง/เส้นทาง, กราฟรายวัน, ตารางรายละเอียดที่จำกัดความสูง และรูปแบบจอเล็ก

โปรดตรวจบน Mac: กด Overview → Exceptions → Scenarios → Definitions; เลือก DC-B / Outer / Overdue open ควรเห็น 9 งานค้างและกราฟรายวันยังใช้ตัวหารทั้งหมดของคลัง/เส้นทาง ตรวจหน้าเมื่อย่อหน้าต่างด้วย ก่อนใช้ภาพหน้าจอสมัครงาน

ขอบเขตการตรวจรุ่นนี้: Python 14 tests, clean builds, CSV/SQL, scenario และ JS filter/syntax ผ่าน แต่ยังไม่ได้ตรวจภาพจริงและ interaction ด้วย browser automation ในเครื่อง build เนื่องจากไม่มี browser binary ที่พร้อมใช้

ฝึกโจทย์ใน docs/guides/PRESENTATION_GUIDE_TH.md และตอบด้วยภาษาตัวเอง ตัวอย่าง OTD 8/10 กับ OTIF 7/10 ต้องแยกได้ ความเข้าใจและการชี้ที่มาของสูตรเป็นส่วนสำคัญของความพร้อมสัมภาษณ์
