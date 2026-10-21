> Historical development note. For current commands and verification scope, start with [README](../../README.md). Counts and pending items below describe that stage.

# Milestone 4 — ข้อเสนอเชิงปฏิบัติการและตรวจการรันใหม่

## รันบน Mac

```bash
cd "/Users/sierra6/Documents/logistics-operations-analytics"
python3 project.py
python3 verify_release.py
open output/dashboard.html
open output/decision_brief.md
```

ควรเห็น 14 tests OK และ status passed จาก verify_release.py ซึ่งตรวจการสร้างรายงานใหม่สองครั้งในโฟลเดอร์ชั่วคราวและเทียบผล CSV/SQL ไม่แก้ข้อมูลส่วนตัวของคุณ

## ผลที่ควรอธิบายได้
- DC-B / Outer: OTIF ต่ำสุด จึงเริ่มตรวจงานค้างและ dispatch/receiving evidence
- DC-C / Outer: เป็น candidate ของ capacity replay ที่ +10% ให้ recovery ต่อ added capacity สูงสุดใน snapshot นี้
- การจัดลำดับสองเรื่องต่างกัน อย่าแนะนำเพิ่มรถเพียงเพราะ OTIF ต่ำ
- ทั้งสองผลมาจากข้อมูลสังเคราะห์ชุดเดิม ไม่ใช่ independent validation
- ผล capacity เป็นขอบเขตบน ไม่มีค่าแรง ค่าน้ำมัน ขนาดรถ สต็อก เวลาโหลด หรือหลักฐานผลต่อ OTIF

รายละเอียดและ proposed owner roles อยู่ใน output/decision_brief.md ส่วนหน้าเว็บแสดงข้อสรุปสำคัญไว้แล้ว

## ขั้นถัดไป
ตรวจหน้ารายงานบน Mac และฝึกอธิบาย 3–5 นาที จากนั้นจัด GitHub repository, ภาพตัวอย่าง, คำอธิบายโครงการและ resume สำหรับตำแหน่งด้านข้อมูลและ operations โดยไม่อ้างประสบการณ์ OMS หรือ Power BI ที่ยังไม่ได้ทำจริง
