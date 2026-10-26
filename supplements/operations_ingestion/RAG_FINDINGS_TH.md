# สรุปหลักฐานก่อนเปลี่ยน retrieval

ตรวจต่อจาก PR #5 commit `35468f2d34d17363f5b1476dd030318052010a45` โดยเก็บ protocol เดิมและรายงาน Mac เดิมทั้งหมดไว้ ผลด้านล่างมาจาก ZIP ที่ผู้ใช้ส่ง 6 ชุด รวม 15 decision calls ที่บันทึกไว้ ไม่ใช่ 15 ตัวอย่างอิสระ และห้ามรวมเป็น accuracy เดียว

## สิ่งที่ยืนยันจาก capture

ตัวตรวจ offline ตรวจลำดับ journal, SHA-256 ของ HTTP bodies, การจับคู่ request/response, การจบ run, raw decision เทียบ report, baseline file hash chain, runtime metadata, model digest ก่อน–หลัง และคำถาม/records เทียบรายงานต้นทางครบ ทั้ง 6 ชุดผ่าน ดู [verified_summary.json](evidence/rag_diagnostics_synthesis/verified_summary.json)

Ollama ที่บันทึกคือ `0.40.7`, generation model `qwen2.5:3b` แบบ Q4_K_M, full digest `357c53fb659c5076de1d65ccb0b397446227b71a42be9d1603d46168015c9e4b` ข้อมูล runtime.json เหมือนกันทุกชุด โหลด context 4096 ตาม /api/ps ที่ตรวจรายรอบ จำนวน token ของเคสที่ล้มเหลวไม่ได้แสดงอาการชนขนาด context แต่ยังไม่ใช่หลักฐานว่าไม่มีกลไก runtime อื่นเกี่ยวข้อง

| ชุดทดลอง | สิ่งที่ส่ง | ผลดิบ | Calls |
|---|---|---|---:|
| วันครบกำหนด baseline | prompt ยาว + schema; order เดียว | insufficient | 1 |
| วันครบกำหนด ไม่มี format | คง request ที่เหลือเหมือน baseline | insufficient | 1 |
| วันครบกำหนด prompt สั้น | ไม่มี format; เปลี่ยนเฉพาะ system | supported | 1 |
| ตรวจ abstention | prompt สั้น ไม่มี format; 7 เคสลบ + due-date control | insufficient ถูก 7/7; control supported 1/1 | 8 |
| อีกสอง false abstentions | prompt สั้น ไม่มี format; records เต็มเคสละ 6 | receiving_window และ quantity ยัง insufficient | 2 |
| ลด context สองเคสเดิม | เปลี่ยนเฉพาะ records: window เหลือ 2, quantity เหลือ 1 | supported ทั้งสอง | 2 |

Captures เป็นหลักฐานจาก HTTP client จริงที่ผู้ใช้ส่ง ไม่ใช่เพียง payload ที่สร้างซ้ำจาก source อย่างไรก็ตามไม่ใช่ packet capture, independent runtime attestation หรือหลักฐาน final model input หลัง template rendering ครบทุกขั้น ข้อมูล effective server defaults และสภาพเครื่องทุกอย่างยังไม่ถูกตรึงได้ทั้งหมด

## ข้อสรุปที่รองรับ

1. **ไม่พบ parser/routing/scoring bug ที่อธิบายสาม false abstentions** ในขอบเขตที่ตรวจ Raw insufficient มาจาก response โดยตรง ไม่ได้ถูกแปลงจาก supported ข้อความนี้ไม่เท่ากับรับรองว่าไม่มีบั๊กอื่นทั้ง repository
2. **ไม่ใช่การ retrieve reference ไม่เจอในสามเคสที่เลือกมาตรวจ** หลักฐานอยู่ในคำขอแล้ว แต่การมีหลักฐานครบไม่ได้ทำให้ model ใช้หลักฐานได้ถูกต้องเสมอ
3. **มีหลักฐาน prompt sensitivity ใน reduced due-date case** เอา format ออกอย่างเดียวไม่เปลี่ยนผล แต่เปลี่ยนเฉพาะ system เป็น prompt สั้นแล้วผลเปลี่ยน ไม่รู้ว่าเกิดจากความยาวหรือถ้อยคำใด
4. **มีหลักฐาน context sensitivity ภายใต้ prompt สั้นในอีกสองเคส** เปรียบเทียบคำขอจริง full กับ reduced ยืนยันว่าเปลี่ยนเฉพาะ records; ข้อความที่เก็บไว้ไม่ถูกแก้ ทั้งสองเปลี่ยนจาก insufficient เป็น supported ยังไม่ระบุ distractor ตัวใดหรือกลไกแน่นอน
5. **prompt สั้นไม่ได้ตอบ supported ทุกกรณีในชุดควบคุมนี้** เคสที่ควรงดตอบทั้งเจ็ดผ่าน ไม่ใช่การรับรอง negative cases ที่ยังไม่เห็นหรือข้อสรุปด้านความปลอดภัยทั่วไป
6. **ยังไม่มีหลักฐานว่าต้องเปลี่ยนเป็นโมเดลใหญ่กว่า** โมเดล/digest เดิมเปลี่ยน decision ได้เมื่อ prompt/context เปลี่ยน แต่ผลนี้ก็ไม่ได้พิสูจน์ว่าโมเดลเดิมเหมาะกับการใช้งานทั่วไป

## สิ่งที่ยังไม่สำเร็จ

- ผลที่ตอบได้หลังลด context ใช้ reference IDs ช่วยเลือก records เป็น oracle-assisted diagnostic ไม่ใช่ retrieval ที่ใช้จริงได้
- ยังไม่ได้ทดสอบ full-context due-date ภายใต้ prompt สั้นในชุดล่าสุด: เคส due-date ที่ผ่านเป็น order เดียว
- Captures ชุดนี้ไม่ได้รัน ID-selection และ materialization ครบเส้นทาง ไม่มีผล end-to-end ใหม่ คะแนน **13/16 reference checks** เดิมจึงคงเดิม ไม่อัปเดตเป็น 16/16 จากการนำผลหลาย protocol มารวมกัน
- Reference checks ยอมรับ required IDs ครบแม้มี extra IDs; human semantic review ยังคง pending ไม่ใช่ semantic accuracy
- ชุด 16 เคสถูกใช้พัฒนาแล้วทั้งหมด ชุดควบคุมและการทดลองซ้ำมีความสัมพันธ์กัน ไม่ใช่ held-out evaluation

## การเปลี่ยนถัดไป

หยุดปรับ decision prompt ที่ได้ผลไปก่อน เก็บ SHORT_DECISION_PROMPT เป็นค่าคงที่ แล้วแยก **การออกแบบ context selector** ออกจากผลที่วัดด้วย oracle ดู [RAG_CONTEXT_SELECTION_DESIGN.md](RAG_CONTEXT_SELECTION_DESIGN.md)

ตัวเลือกแรกที่เสนออย่างระมัดระวังคือ route เฉพาะคำถาม single-field ที่อยู่ใน schema ของ order ไปยัง order record เดิม และคง retrieval เดิมสำหรับคำถามที่ยังจำแนกไม่แน่ชัด ไม่พยายามเลียนแบบ note:TARGET จากชื่อ ID หรือ reference labels ปัจจุบันทำเป็น candidate แบบ opt-in แล้วตาม [คู่มือประเมิน](RAG_CONTEXT_SELECTOR_GUIDE.md) แต่ยังไม่มีผล live แบบครบเส้นทาง และยังไม่อ้างว่าจะซ่อม receiving_window ได้

ก่อนรับ candidate ต้องมีการทดลองครบเส้นทางแบบ version ใหม่ เทียบกับ short-prompt baseline ร่วมสมัยที่ใช้ retrieval เดิม เพื่อแยกผลของ context selector โดยทั้งสองใช้ prompt/schema/options เดียวกัน เก็บ source/digest/requests/counters ครบ แยก 8 answerable, 7 model-abstention และ 1 application gate และเตรียมชุดประเมินที่ยังไม่ถูกใช้ปรับกฎสำหรับข้อสรุปทั่วไป

## ทำซ้ำการตรวจโดยไม่เรียกโมเดล

[verify_capture_chain.py](evidence/rag_diagnostics_synthesis/verify_capture_chain.py) อ่าน ZIP ทั้งหกแบบ read-only และเขียน derived summary ในโฟลเดอร์ใหม่ ตัวอย่าง mapping ของไฟล์อยู่ใน [README](evidence/rag_diagnostics_synthesis/README.md) ไม่ได้เรียก provider หรือตีความข้อความใน note เป็นคำสั่ง

รายงานนี้สังเคราะห์การตรวจที่ทำแล้ว ไม่ใช่การแก้ production หรือการอนุมัติให้ระบบดำเนินงานธุรกิจอัตโนมัติ
