# นำโครงการขึ้น GitHub

## 1. สร้าง repository
เปิด https://github.com/new เลือก owner Quetzel6 ตั้งชื่อ logistics-operations-analytics และเลือก Public

Description: Synthetic logistics analytics with SQL KPIs, exception drill-down, capacity scenarios and reproducible validation.

ไม่เลือก Add README, .gitignore หรือ License ในหน้าเว็บ เพราะไฟล์โครงการมีแล้ว จากนั้นกด Create repository

## 2. รันใน Terminal หลังแตก ZIP รุ่น Portfolio Ready

```bash
cd "/Users/sierra6/Documents/logistics-operations-analytics"
python3 project.py
python3 verify_release.py
git init -b main
git add .
git diff --cached --check
git status --short
git commit -m "Add synthetic logistics analytics portfolio and validation workflow"
git remote add origin https://github.com/Quetzel6/logistics-operations-analytics.git
git push -u origin main
```

คำสั่งชุดนี้สำหรับโฟลเดอร์ที่ยังไม่เคยตั้ง Git หากตั้งไว้แล้วให้ใช้ git status และ git remote -v ก่อน ไม่ต้อง init/add remote ซ้ำ

.gitignore ตัด SQLite, ZIP, cache และ output_seed* แต่ยังเก็บ HTML/CSV/JSON synthetic evidence ที่สร้างซ้ำได้

ถ้า authentication แจ้ง error ส่งข้อความ error มา ไม่วาง token ในไฟล์โค้ดหรือแชท

## 3. ตรวจ GitHub Actions
เปิดแท็บ Actions ของ repo รอ workflow Logistics validation ตรวจ Python 3.10 และ 3.13 ต้องสำเร็จทั้งคู่ก่อนอ้างว่า remote CI ผ่าน

CI ยังไม่ใช่การตรวจหน้าตาใน browser: ตรวจบน Mac เพิ่มด้วยการสลับแท็บ Overview / Exceptions / Scenarios / Definitions และกรอง DC-B / Outer / Overdue open ควรได้ 9 งาน

## 4. สำหรับผู้รับสมัคร
ปักหมุด repo ใน profile หลังตรวจแล้ว ใช้ README, decision brief และ resume bullets ส่วนภาพ Dashboard เก็บหลังตรวจหน้าตาจริง ไม่เผยแพร่ภาพที่ยังไม่ได้ตรวจ

ไม่จำเป็นต้องเปิด GitHub Pages ในขั้นนี้ HTML เปิดแบบ offline ได้ และหน้า GitHub ปกติแสดง source ไม่ใช่ live dashboard
