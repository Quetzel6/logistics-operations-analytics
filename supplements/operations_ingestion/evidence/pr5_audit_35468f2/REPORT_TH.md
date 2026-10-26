# ผลตรวจ PR #5 ก่อนแก้โค้ด

เป้าหมาย: `Quetzel6/logistics-operations-analytics`, commit `35468f2d34d17363f5b1476dd030318052010a45` ตรวจวันที่ 22 ตุลาคม 2026

## ข้อสรุป

ยังไม่มีหลักฐานว่าขนาดโมเดลเป็นสาเหตุ และยังไม่พบข้อผิดพลาดใน parser, stage routing หรือการรวมคะแนนที่อธิบายสาม false abstentions นี้ได้ ข้อมูลที่เก็บไว้แสดงว่าโมเดลคืน `insufficient` โดยตรง; โปรแกรมงดตอบตาม protocol ไม่ได้แปลง `supported` ให้กลายเป็นคำตอบผิด ทั้งสามเคสมี reference evidence อยู่ใน retrieved records ครบ

ยืนยันปัญหาความทนทานของการเก็บผล: ถ้ารันถูกขัดจังหวะ ผลที่เสร็จไปแล้วแต่ยังอยู่ในหน่วยความจำจะไม่ถูกบันทึก และพบข้อความสถานะใน README หลักที่ล้าสมัย ส่วนช่องว่างสำคัญที่สุดต่อการหาสาเหตุคือไม่มี historical HTTP request/response ครบชุด และไม่มี runtime/model identity ที่ใช้เทียบแบบควบคุมได้

ผลตรวจ offline: 99 software tests ผ่านบน Linux/Python 3.12.14; hash ที่มีการบันทึกใน raw reports ทั้งห้าชุดตรงกับ snapshot; fixtures, fingerprint, candidate evidence และ reference labels สร้างซ้ำได้ตรง baseline; คะแนน 13/16 และจำนวน generation 20 ครั้งคำนวณซ้ำได้ตรง; schedule, records hash และ summary ของ diagnostic 24 trials ถูกต้อง ไม่ได้เรียก Ollama หรือ remote model ในการตรวจนี้

## ขอบเขตและการรักษาหลักฐาน

- ตรวจ metadata ของ PR ผ่าน GitHub: head ตรงกับ commit เป้าหมาย, base `5f654ce9d96a18b07c353fc4b853dca01e749e6d` และ PR ยังเปิดอยู่
- checkout เดิมอยู่ที่ base ไม่มี target object จึงสร้าง snapshot แยกที่ `/workspace/audit-pr5-35468f2` จาก base archive แล้วแทนที่ไฟล์ที่เปลี่ยนทั้ง 30 ไฟล์ด้วยเนื้อหาจาก GitHub ที่ตรึง target ref ตรวจ Git blob SHA ของไฟล์ที่ดาวน์โหลดครบ ไม่มีการ checkout/fetch/แก้ไฟล์ใน repo เดิม
- snapshot ไม่ใช่ Git checkout; ห้ามใช้ `git rev-parse HEAD` ใน snapshot เพื่ออ้าง identity ตัว target commit ระบุไว้ในรายงานและ manifest
- ผลดิบเดิมทั้งห้าชุดเก็บครบไม่แก้ไข: `raw_report_hashes.json` ระบุ SHA-256; manifest ของ Git blob อยู่ `/workspace/audit-pr5-file-manifest.json`
- ไฟล์ audit และ offline reproducer อยู่ `/workspace/pr5-audit` แยกจาก source; `reconstructed_requests.json` เป็น payload ที่สร้างซ้ำจากโค้ด ไม่ใช่ request capture จาก Mac
- ไล่ dependency ของ inference/scoring ถึง `assistant.context`, `NoRedirect`, ingestion/fixture normalization, embeddings validation/cosine, ID materialization, evaluator ที่ใช้ร่วมกัน รวมถึง tests, verify.py, README และ workflows ตรวจโครงสร้างส่วนอื่นเพื่อระบุขอบเขต แต่ไม่ได้ทำ semantic audit ทุกฟังก์ชันของ dashboard/PostgreSQL และไม่ได้รัน Docker/PostgreSQL/browser

## ข้อค้นพบที่ยืนยันแล้ว

### B1 — P2: การขัดจังหวะทำให้ผลรันที่เสร็จแล้วสูญหายก่อนบันทึก

ไฟล์: [evaluate_rag_staged.py:84](../../../../supplements/operations_ingestion/evaluate_rag_staged.py:84), [diagnose_rag_context.py:70](../../../../supplements/operations_ingestion/diagnose_rag_context.py:70), [diagnose_rag_context.py:134](../../../../supplements/operations_ingestion/diagnose_rag_context.py:134)

หลักฐาน: evaluators เก็บ rows/trials ใน list แล้วเขียน report เมื่อ evaluate คืนค่าครบเท่านั้น ไม่มี incremental journal หรือ finally สำหรับบันทึก partial results `KeyboardInterrupt` ไม่อยู่ใน `except BriefError` โฟลเดอร์ output ถูกสร้างก่อนเริ่ม และการรันซ้ำ path เดิมถูกปฏิเสธ

ผลกระทบ: Ctrl-C, process termination หรือ exception ที่ไม่ได้จับอาจทำให้ raw outputs ของ calls ที่เสร็จแล้วหายทั้งหมด กระทบการทดลองต่อไปและข้อกำหนดรักษาผลดิบ ไม่มีหลักฐานว่าเหตุการณ์นี้เกิดใน Mac reports ที่ส่งมา ซึ่งครบตามจำนวนที่รายงาน

วิธีทำซ้ำ: `python /workspace/pr5-audit/check_offline.py` ใช้ diagnostic evaluator จริง โดยแทน `generate` ให้ trial แรกคืน supported และครั้งที่สองยก KeyboardInterrupt; ตรวจว่า trial แรกเสร็จแล้ว แต่ output directory ว่าง ทำทุกอย่างใน temp directory ไม่เรียกโมเดล

ความมั่นใจ: สูง ยืนยันด้วยโค้ดและ offline reproduction ก่อน live experiment รอบใหม่ควรแก้การบันทึกใน branch แยก หลังพิจารณารายงานนี้

### B2 — P3: README หลักให้สถานะ model execution ที่ไม่ตรงหลักฐานล่าสุด

ไฟล์: [README.md:9](../../../../README.md:9), เปรียบเทียบ [supplement README:25](../../../../supplements/operations_ingestion/README.md:25)

หลักฐาน: README หลักระบุ “Model execution remains unverified and paused” ขณะที่ supplement อธิบาย owner-run Mac results และรายงานที่เก็บไว้ ส่วนของคำอธิบายนี้ไม่ได้ผูกกับ milestone เก่าอย่างชัดเจน

ผลกระทบ: ผู้อ่านเริ่มจาก root อาจเข้าใจว่าไม่เคยมี live execution; ไม่กระทบคะแนน ควรบอกว่า owner-run มีแล้ว แต่ independent runtime attestation/human review ยังขาด

วิธีทำซ้ำ: อ่านสองตำแหน่งข้างต้นใน target commit เทียบกัน ความมั่นใจ: สูงสำหรับข้อความไม่สอดคล้อง; ต่ำต่อผลต่อการตัดสินใจของผู้อ่านแต่ละคน

## ช่องว่างของหลักฐานและข้อจำกัด

### E1 — P1 ต่อข้อสรุปเชิงสาเหตุ: ไม่มี historical wire payload/response ครบ

ไฟล์: [local_rag_staged.py:50](../../../../supplements/operations_ingestion/local_rag_staged.py:50), [local_rag.py:47](../../../../supplements/operations_ingestion/local_rag.py:47), [diagnostic raw report:282](../../../../supplements/operations_ingestion/evidence/local_rag_context_mac/report.json:282)

หลักฐาน: generate ส่ง dict ไป transport แล้ว trace เก็บเพียง response text/done_reason และ flags; post serialize ด้วย `json.dumps(payload).encode()` แต่ไม่ได้เก็บ request bytes หรือ full response envelope ข้อมูล `done`, returned model, prompt_eval_count, eval_count และ timings ถูกตรวจหรือทิ้ง ไม่ถูกเก็บครบ Embeddings vectors/similarity scores ก็ไม่ได้เก็บ

payload ที่สร้างซ้ำได้: POST loopback `/api/generate`, `model=qwen2.5:3b`, `stream=false`, `system=DECISION_PROMPT`, `format=DECISION_SCHEMA`, `prompt` เป็น JSON string มีเพียง question กับ records, `options={temperature:0,num_predict:1600}` selection ใช้ question/records เดียวกัน เปลี่ยน system/schema ให้เลือกเฉพาะ IDs ที่ retrieve แล้ว ไม่มี reference labels ถูกแนบเป็น field; reduced context ใช้ labels เลือก records ก่อนส่งเท่านั้น

embedding path เป็น `/api/embed`, `truncate=false`; สำหรับ `nomic-embed-text:v1.5` เติม search_query/search_document prefix ถูกตำแหน่ง จำนวน vectors ตรง 1+candidate count ผ่าน validation ก่อนจัดอันดับ order ถูกตรึงไว้ก่อน แล้วเลือกอีกสูงสุดห้ารายการ ไม่มี raw vectors ให้จัดอันดับของ Mac ซ้ำอย่างอิสระ

ผลกระทบ: ตรวจ source-level request construction ได้ แต่ยังพิสูจน์ไม่ได้ว่า Mac ส่ง bytes นี้จริง หรือ Ollama render system/template/schema เป็น model input อย่างไร ไม่พบการส่งผิด field จากโค้ดที่ตรวจ แต่ไม่ใช่การยืนยัน wire/runtime

วิธีทำซ้ำ: รัน offline script แล้วอ่าน reconstructed_requests.json เทียบ trace ใน raw reports จะเห็นส่วนที่สร้างซ้ำได้และส่วนที่ไม่ได้บันทึก ระดับความมั่นใจ: สูงว่าข้อมูลขาด; ยังไม่ทราบว่ามี transport/template bug จริงหรือไม่

### E2 — P1 ต่อการเปรียบเทียบ: model name เท่ากันยังยืนยัน runtime เท่ากันไม่ได้

ไฟล์: [evaluate_rag_staged.py:60](../../../../supplements/operations_ingestion/evaluate_rag_staged.py:60), [diagnose_rag_context.py:64](../../../../supplements/operations_ingestion/diagnose_rag_context.py:64), [diagnose_rag_context.py:94](../../../../supplements/operations_ingestion/diagnose_rag_context.py:94)

หลักฐาน: เก็บ model tag/Python/platform/source hashes; diagnostic บังคับ tag เท่ากับ baseline แต่ไม่ได้ตรวจ full digest, Ollama version, template, model parameters/Modelfile, effective num_ctx, seed หรือ runtime hardware/options ค่า num_ctx/seed ไม่ได้ตรึงใน request ไม่ได้แปลว่าผิดหรือ context ถูก truncate เพียงแต่ไม่ทราบค่าจริง ข้อมูล short IDs ในข้อความผู้ใช้ยังไม่ใช่ runtime metadata ที่ผูกกับแต่ละ trial

ผลกระทบ: source hashes ที่ตรงกันยืนยันความสอดคล้องภายใน artifact ได้ แต่ไม่ใช่การรับรองว่ารายงานมาจาก binary/model/runtime นั้นจริง ผล 4/4 ที่ temperature=0 อาจสัมพันธ์กันสูง ไม่ใช่สี่ตัวอย่างอิสระ ใช้เทียบ descriptive behavior ได้ แต่ยังสรุปเหตุจาก model size, context หรือ prompt อย่างเด็ดขาดไม่ได้

วิธีทำซ้ำ: ตรวจ keys ในรายงานและ payload จาก offline script; ไม่มี metadata ดังกล่าว เก็บ `/api/version`, `/api/tags` full digests, `/api/show` ของทั้งสองโมเดล, template/parameters และ runtime configuration ก่อนการทดลองใหม่ ความมั่นใจ: สูง

### E3 — P2: reference checks ยอมรับ evidence ส่วนเกินและไม่ตรวจ semantic correctness

ไฟล์: [evaluate_rag_challenge.py:58](../../../../supplements/operations_ingestion/evaluate_rag_challenge.py:58), [local_rag_ids.py:53](../../../../supplements/operations_ingestion/local_rag_ids.py:53), [test_rag_staged.py:23](../../../../supplements/operations_ingestion/tests/test_rag_staged.py:23)

หลักฐาน: score ผ่านเมื่อ status ตรงและ required IDs ครบ แม้ selected_extra_ids ไม่ว่าง เป็นเจตนาที่เขียนไว้ชัดเจน materialize ตรวจ membership/count/uniqueness แล้ว copy text ไม่ตรวจว่าทุก ID เกี่ยวข้อง mocks กำหนด vectors ให้ note เป้าหมายติด ranking และส่ง JSON decision/selection ที่เลือกไว้ล่วงหน้า จึงไม่ได้จำลอง tokenizer, model template, structured decoder หรือ semantics ของ Ollama tests ตรวจรูปแบบอย่างมีประโยชน์ แต่ไม่สามารถจับโมเดลงดตอบผิดได้ เว้นแต่ระบุผลโมเดลนั้นเข้า mock

ผลกระทบ: 13/16 เป็น reference checks ตามนิยาม ไม่ใช่ semantic accuracy หรือหลักฐานป้องกัน prompt injection ได้ครบ ยังไม่ใช่ scoring bug และไม่พบว่า scorer ลงโทษคำตอบที่มี reference ครบในสามเคสนี้ unknown-order gate ถูกแยกจาก 7 model abstentions ถูกต้อง

วิธีทำซ้ำ: ดู return expression ของ score; เรียก score ด้วย required ID พร้อม unrelated ID จะยังผ่านและรายงาน extra IDs หรือเรียก tests ซึ่งใช้ fixed responses ความมั่นใจ: สูง การปรับ metric ควรออก version ใหม่ ไม่คำนวณทับ raw reports เดิม

## ตรวจสาม false abstentions

ตำแหน่งหลักฐาน: [diagnostic contexts:24](../../../../supplements/operations_ingestion/evidence/local_rag_context_mac/report.json:24), [quantity:74](../../../../supplements/operations_ingestion/evidence/local_rag_context_mac/report.json:74), [due date:119](../../../../supplements/operations_ingestion/evidence/local_rag_context_mac/report.json:119)

| เคส | fact ที่อยู่ใน source/retrieved records | full/reduced records | supported full/reduced |
|---|---|---|---|
| receiving_window | note:TARGET ระบุ 2026-11-01 09:00–11:00 UTC พร้อมข้อความ cause unverified | 6 / 2 | 0/4 / 0/4 |
| quantity_with_cause_context | order:T201 ระบุ quantity=246 | 6 / 1 | 0/4 / 4/4 |
| due_date_with_instruction | order:T204 ระบุ due_date=2026-12-06; full มี instruction note วันที่ปลอม 2099-01-01 | 2 / 1 | 0/4 / 0/4 |

ทั้งสาม reference labels สอดคล้องคำถามและ fixture ต้นทาง สร้าง bundle → ingest → context ซ้ำตรง candidate records และ fingerprint ของรายงาน baseline raw decision เป็น insufficient และ selection ไม่เริ่ม; strict parser ไม่ได้แก้หรือกลับค่าคำตอบ ไม่มีคำตอบจาก selection ให้ scorer ตีผิดในสามเคสนี้

reduced due-date เหลือ `Order T204; due_date=2026-12-06; quantity=73.` จริง ไม่มี instruction note อยู่ใน payload ที่สร้างซ้ำจาก diagnostic ดังนั้นการมี instruction note ใน request นั้นอธิบายผล reduced โดยตรงไม่ได้ แต่ยังไม่ตัด runtime/template effects หรือปฏิสัมพันธ์อื่น เพราะไม่มี wire/runtime capture

วิธีทำซ้ำทั้งหมด: offline script ตรวจ hashes, fixtures, labels, baseline scoring/routing, exact copied quotes, diagnostic contexts/schedule/records hashes/raw decisions และ summaries ความมั่นใจ: สูงสำหรับความสอดคล้องของ artifacts; ยังไม่มี independent live reproduction

## โครงสร้าง, คำสั่งทำซ้ำ และ CI

เส้นทางสำคัญเป็น Python stdlib ไม่มี framework ซ่อน prompt เพิ่มใน dependency: ingest → SQLite → assistant.context → embed/check vectors → cosine top-six พร้อม order → decision → selection เฉพาะ supported → materialize → score/HTML escape `assistant.PROMPT` และ remote Responses API เป็นเส้นทางแยก ไม่ได้ถูกใช้เป็น staged system prompt

context จำกัด 20 events และ 10 note IDs; note เกิน 1500 ตัวอักษรถูก withheld พร้อม warning (assistant.py:34 เป็นต้นไป) จึงไม่ใช่ complete order history แต่ไม่กระทบ required evidence ของสามเคสที่ตรวจ tests ครอบคลุม bounded retrieval และ input validation ไม่พบ dependency เพิ่มเติมที่ต้องติดตั้งเพื่อทำ offline audit

คำสั่งใน staged/context guides ตรง CLI และ exit 1 ของ baseline เมื่อไม่ผ่านครบ 16 เป็นพฤติกรรมตั้งใจ ไม่ใช่ transport failure ส่วน diagnostic exit 0 เมื่อทั้ง 24 คืน decision ที่ valid แม้เป็น insufficient ทั้งหมดก็ถูกต้องตามวัตถุประสงค์ แยก software validity จาก quality

GitHub API ยืนยัน workflows ที่ target commit ผ่านทั้งสองรายการ:

- [Operations ingestion supplement run 39745768063](https://github.com/Quetzel6/logistics-operations-analytics/actions/runs/39745768063)
- [Logistics validation run 39745768058](https://github.com/Quetzel6/logistics-operations-analytics/actions/runs/39745768058)

อ่าน workflow YAML แล้ว verify.py ใช้ unittest discovery และ SQLite acceptance; ไม่มี Ollama invocation ไม่ได้อ่าน job logs ทุก job และไม่ได้ rerun CI สถานะ success จึงใช้ยืนยัน workflow outcome เท่านั้น

## สมมติฐานและการทดลองขั้นต่ำที่เสนอ — ยังไม่ดำเนินการ

เริ่มที่ reduced due-date เพราะมี record เดียวและไม่ต้อง embeddings/retrieval หลังเก็บ runtime metadata และทำ durable request/response capture ใน branch แยก ให้เก็บ request bytes ก่อนส่ง, full response ก่อน parse, timestamps/call IDs/endpoint รวมถึง hashes และ effective configuration ห้ามทับรายงานเดิม ไม่ต้อง pull โมเดลใหม่

| สมมติฐาน | หลักฐานปัจจุบัน | การทดลองขั้นต่ำ / สิ่งที่แยกได้ |
|---|---|---|
| structured-output/schema มีผลต่อ decision | ยังไม่มีหลักฐานยืนยัน | replay exact reduced due-date request 1 ครั้ง แล้วอีก 1 ครั้งตัดเฉพาะ format ออก คง system/prompt/model/options เดิม ถ้าต่างกันเป็นเบาะแส decoder/schema interaction ยังไม่พิสูจน์เหตุทั่วไป |
| enum order มี bias | ยังไม่มีหลักฐานยืนยัน; schema ปัจจุบันเรียง supported ก่อน | หากต้องตามต่อ 1 ครั้งสลับเฉพาะ enum order เทียบ captured baseline ไม่แก้ parser ไม่เรียกผลที่เปลี่ยนว่าการแก้สำเร็จจากครั้งเดียว |
| system/template ไม่ถูกนำไปใช้ตามคาด | โค้ดส่ง system ถูก field แต่ไม่มี template/runtime attestation | อ่าน /api/show ก่อน; ถ้ายังสงสัย ใช้ sentinel instruction ที่ไม่อาศัยความรู้ 1 ครั้งเป็น control แยก ห้ามปนเข้าคะแนนเดิม การผ่าน sentinel ก็ไม่รับรอง prompt ทั้งหมด |
| cause/background รบกวน quantity | สอดคล้องกับ full 0/4 reduced 4/4 | หลัง reproduce ภายใต้ captured runtime จึงเพิ่มทีละ record กลับเข้า quantity เทียบ reduced; ไม่จำเป็นต้องเริ่มจาก 24 calls ใหม่ |
| representation due_date ทำให้โมเดลไม่เข้าใจ | ยังไม่มีหลักฐานยืนยัน | ถ้า baseline reproduce ได้ เปลี่ยนเฉพาะ text เป็นประโยค due date โดยคง fact/schema/system เดิม 1 ครั้ง เก็บเป็น diagnostic ใหม่ ไม่ใช่ end-to-end score |
| context truncation | ไม่มีหลักฐาน prompt token counts; reduced สั้นมากก็ยังล้มเหลว | ตรวจ prompt_eval_count/effective num_ctx ก่อนเพิ่ม context ห้ามอ้างว่าเป็นสาเหตุจากการเดา |
| model size เป็นเหตุ | ยังแยกจาก template/weights/quantization/runtime ไม่ได้ | ยังไม่ควรเริ่มด้วยเปลี่ยนโมเดล หากเปลี่ยนภายหลังต้องตรึง payload และเก็บ identities ครบ ใช้ held-out set สำหรับข้อสรุปคุณภาพทั่วไป |

ไม่มี live experiment, environment change, model download หรือ source fix ในรอบนี้ รายงานและ reproduction artifacts พร้อมให้พิจารณาก่อนเปิด branch แก้ไข
