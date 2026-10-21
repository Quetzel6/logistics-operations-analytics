> Historical development note. For current commands and verification scope, start with [README](../../README.md). Counts and pending items below describe that stage.

# Milestone 2 — รายการปัญหาและแนวโน้มรายวัน

## ติดตั้งบน Mac
แตกไฟล์ ZIP นี้ทับโฟลเดอร์เดิมใน Documents ได้ เพราะเก็บเส้นทาง logistics-operations-analytics เหมือนเวอร์ชันแรก ข้อมูลทั้งหมดเป็นข้อมูลสังเคราะห์ที่สร้างซ้ำได้

```bash
cd "/Users/sierra6/Documents/logistics-operations-analytics"
python3 -m unittest discover -s tests -q
python3 project.py
open output/dashboard.html
```

ผลที่ควรได้: 9 tests, OK; quality_gate: passed; 168 trips, 1339 orders

## ทดสอบบนหน้าเว็บ
1. เลื่อนลงส่วน Daily service and exception worklist
2. เลือก DC-B / Outer แล้วดูจำนวนงานค้างและงานส่งช้า
3. เลือก Short shipment เพื่อดูงานที่ส่งไม่ครบ
4. เปลี่ยนประเภทปัญหาแล้วตรวจว่าตาราง Daily ไม่เปลี่ยนตาม เพราะตัวหารยังต้องรวมงานส่งสำเร็จด้วย
5. เปลี่ยน Warehouse/Route กลับ All เพื่อตรวจรายการทั้งระบบ

ตัวกรองมีผลเฉพาะส่วนรายละเอียด ไม่เปลี่ยน summary card ด้านบน หน้าเว็บแจ้งขอบเขตนี้ไว้แล้ว

## สิ่งที่เพิ่ม
- รายการปัญหาไม่ซ้ำ order แม้มีหลาย flags
- จำนวนวันที่ช้าและจำนวนหน่วยที่ส่งไม่ครบ
- Daily performance แยกตาม promised date ประเมิน ณ วันตัดยอด
- CSV exceptions.csv และ daily.csv
- กรณีมีวันส่งหลังวันตัดยอด นับเป็น open ณ snapshot
- Python tests 9 ข้อ และ JavaScript filter/reconciliation checks

ขั้นต่อไป: scenario เชิงทรัพยากรพร้อมสมมติฐานและ stress cases ยังไม่อ้างผลลดต้นทุนหรือเพิ่ม OTIF จริง
