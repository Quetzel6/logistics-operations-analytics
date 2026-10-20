# M4: หลักฐานล่าสุด, human review และ PostgreSQL query lab

## อัปเดตผลจากผู้พัฒนาโปรเจกต์บน Mac

50 tests และ baseline 8/8 ผ่าน; PostgreSQL benchmark ผ่าน (5.458 → 0.048 ms เฉพาะ query ในการทดลอง); ตรวจ review scenarios ครบแปดและแจ้งว่าไม่พบปัญหา แต่ยังไม่มีคะแนนแยกเกณฑ์หรือเวลาที่วัดจริง ดู AUTHOR_VERIFICATION_M4.json และ CASE_STUDY.md ส่วนสถานะด้านล่างเป็นประวัติของชุดส่งมอบก่อนทดสอบ Mac

## สถานะ ณ ชุดส่งมอบเดิม

- Linux/Python 3.12: unit tests 50 ข้อผ่าน, baseline regression 8/8, pipeline รันซ้ำผ่าน
- Review packet 8 กรณี: required evidence ตามที่ผู้พัฒนากำหนดไม่ตกหล่น แต่ **ยังรอคุณประเมิน** ด้าน relevance, unsupported claims, action suitability และ clarity
- PostgreSQL benchmark: เตรียมโค้ดแล้ว แต่เครื่องพัฒนาไม่มี Docker จึง **ยังไม่ยืนยันผลรัน**
- ไม่เรียก OpenAI หรือบริการโมเดลใด ๆ และไม่ต้องมี API key
- ผล Mac และ GitHub CI จาก M3 ไม่ใช่ผลยืนยันโค้ด M4 นี้

## 1. เริ่มในโฟลเดอร์ใหม่บน Mac

แตก ZIP ไปยัง Documents/Operations_M4 แล้วเปิด Terminal:

```bash
cd "/Users/sierra6/Documents/Operations_M4/operations-ingestion-lab"
python3 verify.py
python3 evaluate_assistant.py
python3 pipeline.py --bundle fixtures --output output/mac-m4-pipeline
python3 pipeline.py --bundle fixtures --output output/mac-m4-pipeline
```

คาดหวัง 50 tests OK, baseline 8/8 และ pipeline passed_local ทั้งสองครั้ง การรันซ้ำใช้ output เดิมเพื่อทดสอบ replay ส่วน report แต่ละรอบอยู่ใน runs คนละโฟลเดอร์

## 2. สร้างและอ่านชุดประเมิน

```bash
python3 review_packet.py generate --directory output/mac-m4-review
open output/mac-m4-review/review.html
```

ใช้โฟลเดอร์ใหม่: คำสั่ง generate จะไม่เขียนทับโฟลเดอร์เดิม เพื่อป้องกันการลบผลประเมิน

อ่านแต่ละกรณี แล้วแก้ `output/mac-m4-review/decisions.json` ใน VS Code:

- ใส่ชื่อหรือชื่อย่อคุณใน reviewer
- ทุกกรณีมี 4 เกณฑ์: relevance, unsupported_claims, action_suitability, clarity
- เปลี่ยน rating จาก pending เป็น pass หรือ fail และใส่ rationale อธิบายเหตุผล
- สำหรับ unsupported_claims ให้ pass เมื่อไม่พบข้อสรุปเกินหลักฐาน
- ห้ามแก้ packet.json หลังเริ่ม review; ระบบตรวจ hash ว่าผลที่ประเมินยังเป็นชุดเดิม
- ไม่จำเป็นต้องให้ผ่านทุกข้อ หากสื่อความหมายไม่ชัดหรือไม่ช่วยตัดสินใจ ให้ fail พร้อมเหตุผล

จากนั้น:

```bash
python3 review_packet.py score --directory output/mac-m4-review
```

หากยังไม่ประเมินต้องเห็น pending_cases=8 และ passed_cases=0 ผลนี้เป็น self-reported human review ไม่ใช่ independent benchmark หรือหลักฐานประหยัดเวลาธุรกิจ

## 3. PostgreSQL benchmark (เปิด Docker Desktop ก่อน)

```bash
docker info
python3 postgres_benchmark.py --output output/mac-m4-postgres
```

ครั้งแรก Docker อาจดาวน์โหลด postgres:16-alpine ต้องมีอินเทอร์เน็ต แต่ไม่มีการเรียกโมเดล Container สร้างชื่อเฉพาะ ไม่เปิด port ให้ host และลบทิ้งเมื่อเสร็จ ใช้ข้อมูลสังเคราะห์แยกจากฐานเดิม ไม่ต้องใส่รหัสผ่านของฐานที่คุณใช้งานอยู่

ส่งผล JSON สุดท้ายกลับมา หาก status ไม่ใช่ passed_local ให้หยุดสรุปผล benchmark ไว้ก่อน ผลละเอียดอยู่ที่ output/mac-m4-postgres/postgres_benchmark.json หาก Docker ยังไม่พร้อม ให้แก้ให้พร้อมและใช้ output ชื่อใหม่เมื่อรันอีกครั้ง เช่น output/mac-m4-postgres-02

สิ่งที่ต้องตรวจ:

- orders=50000, events=200000, notes=1000, quantity_total=2525000
- results_match_expected=true
- constraint_rejections=3 ในไฟล์รายงาน
- container_removed=true
- เปรียบเทียบ median และ query plan ตามผลจริง ไม่มีเกณฑ์บังคับว่า index ต้องเร็วกว่า

หาก cleanup ไม่สำเร็จ ให้ตรวจ container ที่มีชื่อ operations-pg-lab-* และ label portfolio.lab=operations-m4 ก่อนลบเฉพาะตัวที่สคริปต์นี้สร้าง ห้ามใช้ docker system prune

## ทักษะและการประยุกต์ใช้งาน

Data engineering: สัญญาข้อมูล, grain/keys, validation, rollback/replay, reconciliation และ PostgreSQL query plan ที่รันผ่านจริง

Operations decision support: ตัวอย่าง exception review, หลักฐานอ้างอิง, คำเตือนข้อมูลขาด/ประวัติไม่ครบ, abstention และ rubric ที่คนตรวจจริง

ไม่อ้างว่าเป็น Agentic AI, LLM inference สำเร็จ, Airflow, data lake, production deployment, manufacturing connector หรือผลงานลดต้นทุนจริง และไม่ใช้โปรเจกต์แทนปีประสบการณ์ทำงาน

ขั้นถัดไปหลัง Mac และ review: ตรวจข้อผิดพลาดที่คุณพบ แก้ให้ผ่าน แล้วปรับ README/เรซูเม่/จดหมายให้ตรงหลักฐานล่าสุดก่อนยื่น
