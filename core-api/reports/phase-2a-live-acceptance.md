# PHASE 2A LIVE ACCEPTANCE

Generated at: 2026-08-11T20:20:35.307608+00:00

## Materialize Real Data

RAW trusted order rows: **110**
RAW unsafe/foreign rows: **107**

### First run

| table | inserted | updated | skipped | unsafe |
| --- | --- | --- | --- | --- |
| canonical_orders | 107 | 0 | 3 | 107 |
| canonical_sales | 100 | 0 | 10 | 107 |
| canonical_sale_items | 471 | 0 | 10 | 107 |

### Second run

| table | inserted | updated | skipped | duplicates |
| --- | --- | --- | --- | --- |
| canonical_orders | 0 | 107 | 3 | 0 |
| canonical_sales | 0 | 100 | 10 | 0 |
| canonical_sale_items | 0 | 471 | 10 | 0 |

## Organization Breakdown

| organization | trusted_raw_orders | unsafe_raw_orders | canonical_orders | canonical_sales | canonical_sale_items | orders_with_items | orders_without_items | sales_with_customer | sales_without_customer | total_order_amount | total_realized_sale_amount |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Администрация | 0 | 107 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| MODAILY | 95 | 0 | 95 | 88 | 432 | 88 | 7 | 88 | 0 | 292902270.0000 | 292902270.0000 |
| MODAILY ANDIJON | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| MODAILY NAMANGAN | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| MODAILY QOQON VA FARGONA | 10 | 0 | 10 | 10 | 26 | 10 | 0 | 10 | 0 | 20138300.0000 | 20138300.0000 |
| MODAILY SURXANDARYO | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| SAMO SERVIS | 2 | 0 | 2 | 2 | 13 | 2 | 0 | 2 | 0 | 5517000.0000 | 5517000.0000 |

## Order vs Sale by SmartUp Source Status

| source_status_code | count | canonical_order_status | creates_canonical_sale_yes | creates_canonical_sale_no | reason |
| --- | --- | --- | --- | --- | --- |
| <NULL> | 3 | unmapped | 0 | 3 | no sold_quant and no positive line amount |
| A | 71 | approved | 65 | 6 | details[].sold_quant > 0 |
| B#N | 21 | new | 21 | 0 | details[].sold_quant > 0 |
| B#S | 11 | unmapped | 11 | 0 | details[].sold_quant > 0 |
| B#V | 2 | unmapped | 2 | 0 | details[].sold_quant > 0 |
| C | 2 | cancelled | 1 | 1 | no sold_quant and no positive line amount |

## Realization Evidence Audit

canonical_sales создаются только если в order row есть explicit realization evidence: сначала сумма details[].sold_quant > 0, иначе любой positive line sold_amount/amount > 0. Сам source status сам по себе sale не создаёт.

| evidence_type | sales_count |
| --- | --- |
| sold_amount | 1 |
| sold_quant | 99 |

## Money Reconciliation

| result | count |
| --- | --- |
| exact_match | 100 |
| cannot_verify | 7 |

## Quantity Reconciliation

| metric | value |
| --- | --- |
| RAW ordered units | 1982 |
| Canonical ordered units | 1982.0000 |
| RAW sold units | 1975 |
| Canonical sold units | 1975.0000 |
| RAW returned units | 0 |
| Canonical returned units | 0.0000 |

## Known Deal Trace — deal_id 268805991

| organization | request_filial_id | response_filial_id | trust_status | enters_canonical_orders | enters_canonical_sales | enters_canonical_sale_items | raw_record_id |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Администрация | None | None | RESPONSE_FILIAL_DIFFERS | False | False | False | ada81062-ea46-5ef1-923a-e287680f9aa4 |
| MODAILY QOQON VA FARGONA | None | None | TRUSTED | True | True | True | 199d7c54-169c-589f-8e7c-88aaa1274057 |

## Customer Linkage

Linked: **207**  
Unresolved: **0**  
Identifier absent: **0**

| organization | order_or_sale | customer_source_id | canonical_customer_id | customer_name | customer_quality |
| --- | --- | --- | --- | --- | --- |
| MODAILY | 266781320 | 20054490 | 70dcef99-ff46-562c-897c-9f85bc394de2 | SAYFULLAYEVA MUXLISA SHUKURILLA QIZI | partial |
| MODAILY | 266784100 | 18491668 | 3fef4fd7-66e1-5208-8987-edfdc77bdd2d | MUXAMMEDOVA SABINA AVAZ QIZI | partial |
| MODAILY | 266802977 | 20467399 | cba763e2-4108-5c94-823f-a4ecf0433982 | UNIVERSAL-FARM-PLUS МЧЖ | partial |
| MODAILY | 266804078 | 19562997 | 60e92b77-11bb-50bf-b182-b6fb9948ba71 | Shodiyova Asaloy Asqar qizi | partial |
| MODAILY | 266811602 | 18879680 | b0b3fa60-a0b4-5b71-9d90-ea6506351a34 | ЧП "SOLIHA QUDDUS" O'RIKZOR 1-18 подвал | partial |
| MODAILY | 266982666 | 17835029 | ecec6535-43fd-5b5b-ab8f-73ff5ccbdb80 | MADINAPA KENAYE | partial |
| MODAILY | 267049912 | 18629335 | 865515d9-3514-5d0b-a5c3-c1e7c07add2a | ROZIKOVA MAXLIYO AZAMATOVNA | partial |
| MODAILY | 266964237 | 18719734 | f41d2372-7c1c-55f8-92f1-cd00dbc7876a | AXMETOVA MOHINUR | partial |
| MODAILY | 266896277 | 19228491 | ae14edb6-2269-5a1d-8894-0090a7c21bc9 | ELOV ASQAR KAMOLOVICH 6-10 | partial |
| MODAILY | 267049916 | 18656980 | 771de055-a212-5d77-9de7-44d8da21639a | Miss ledi parfyumerya kosmetika _ 116 dòkon. | partial |
| MODAILY | 266941111 | 18759684 | 0d860323-0abc-503b-b7f9-5bcd23108885 | Azizov Adxam | partial |
| MODAILY | 266776845 | 20079692 | e8718620-160a-559a-b080-d84790cd5435 | G‘AYIBOVA LATOFAT BEKTURDI QIZI | partial |
| MODAILY | 266780917 | 18457316 | e1f259f5-4f13-5853-b3c1-e269a33d55ab | SAIDAXMEDOV BAXODIRXON RAVSHANOVICH | partial |
| MODAILY | 266853338 | 16165547 | 3fd21b4f-6d74-5184-88ff-366806c20c0b | QURBONOVA SHIRMONOY ABDURAXMONOVNA | partial |
| MODAILY | 267348211 | 16139252 | ade6777a-bf14-52a6-9ff0-b70a5ad2308e | SHERMUXAMEDOV ABDUGAFFOR | partial |
| MODAILY | 267034365 | 16155812 | 9ec39ab1-53ca-5691-84a1-1ebf8220ce63 | "TOSHKENT-PARFUM" MCHJ | partial |
| MODAILY | 267212647 | 18301544 | 6fbb1508-2661-5315-8972-8529cd228377 | YULDASHEV SAXOBIDDIN XUSANMAT O‘G‘LI | partial |
| MODAILY | 267368905 | 20474436 | 480ee6a1-8978-51a8-8159-e93337b09b98 | ombor uz | partial |
| MODAILY | 266959624 | 16161944 | c2ddd0fc-7dd3-5209-bfb9-184f1783a941 | TURAYEVA SITORA O‘KTAM QIZI | partial |
| MODAILY | 267035952 | 16140380 | c782d724-a1c8-51ea-a940-12b2429d21a9 | IFOR TOYS XK | partial |

## Product Linkage

Linked: **471**  
Unresolved: **0**  
Identifier absent: **0**

| order | source_product_id | canonical_product | product_name | ordered_qty | sold_qty | unit_price | amount |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 266781320 | 966 | 9d362936-7b1f-5cf7-8540-f0789a2af7e2 | BALANCING FOAM CLEANSER/ 150ml [966] | 3.0000 | 3.0000 | 143500.0000 | 430500.0000 |
| 266781320 | 935 | 36e59086-f4af-5e07-bb4d-42d21bcc9e7b | DAILY MOISTURE SPF PA++++ 50+/ 50ml [935] | 5.0000 | 5.0000 | 151500.0000 | 757500.0000 |
| 266784100 | 973 | c71315b9-a731-51db-b9e8-0457565a700c | BALANCE PURIFYING GEL CLEANSER/ 200ml [973] | 1.0000 | 1.0000 | 148200.0000 | 148200.0000 |
| 266784100 | 000 | 51bfe133-5e85-52c9-b1a1-dc81d3ab9e21 | ELASTIC GLOW PERFECTING TONER/ 100ml [000] | 1.0000 | 1.0000 | 129700.0000 | 129700.0000 |
| 266784100 | 959 | 4d0b5376-4a44-5049-a55a-e92115002743 | REFINE & RENEW B3 SERUM/ 30ml [959] | 1.0000 | 1.0000 | 229600.0000 | 229600.0000 |
| 266784100 | 942 | 53db113a-f40b-55e6-a542-794da796513e | RETINAGE FIRMING SERUM/ 30ml [942] | 1.0000 | 1.0000 | 257100.0000 | 257100.0000 |
| 266802977 | 973 | c71315b9-a731-51db-b9e8-0457565a700c | BALANCE PURIFYING GEL CLEANSER/ 200ml [973] | 12.0000 | 12.0000 | 148200.0000 | 1778400.0000 |
| 266802977 | 966 | 9d362936-7b1f-5cf7-8540-f0789a2af7e2 | BALANCING FOAM CLEANSER/ 150ml [966] | 12.0000 | 12.0000 | 143500.0000 | 1722000.0000 |
| 266802977 | 904 | ab68079a-815a-5c9b-a2e4-263f8b32c087 | DAILY GLOW HYDRATING CREAM/ 50ml [904] | 12.0000 | 12.0000 | 192400.0000 | 2308800.0000 |
| 266802977 | 935 | 36e59086-f4af-5e07-bb4d-42d21bcc9e7b | DAILY MOISTURE SPF PA++++ 50+/ 50ml [935] | 12.0000 | 12.0000 | 151500.0000 | 1818000.0000 |
| 266802977 | 000 | 51bfe133-5e85-52c9-b1a1-dc81d3ab9e21 | ELASTIC GLOW PERFECTING TONER/ 100ml [000] | 12.0000 | 12.0000 | 129700.0000 | 1556400.0000 |
| 266802977 | 911 | e6edbf75-b490-5f24-a2fb-555da0167ff0 | NIGHT RECOVERY CREAM/ 50ml [911] | 12.0000 | 12.0000 | 217800.0000 | 2613600.0000 |
| 266802977 | 997 | 13f987b7-9b2c-5f34-a57d-027df3faf7be | ONSEN THERAPY MIST/ 120ml [997] | 12.0000 | 12.0000 | 154500.0000 | 1854000.0000 |
| 266802977 | 959 | 4d0b5376-4a44-5049-a55a-e92115002743 | REFINE & RENEW B3 SERUM/ 30ml [959] | 12.0000 | 12.0000 | 229600.0000 | 2755200.0000 |
| 266802977 | 942 | 53db113a-f40b-55e6-a542-794da796513e | RETINAGE FIRMING SERUM/ 30ml [942] | 12.0000 | 12.0000 | 257100.0000 | 3085200.0000 |
| 266802977 | 980 | 134b8913-bfde-5017-8c62-5c7fd42d16c7 | SILK TOUCH HAND CREAM/ 80ml [980] | 12.0000 | 12.0000 | 72700.0000 | 872400.0000 |
| 266802977 | 928 | 3f3fb28e-63a7-53c0-905c-3ef86cac64b3 | SKIN LIFTING COLLAGEN CREAM/ 50ml [928] | 12.0000 | 12.0000 | 219300.0000 | 2631600.0000 |
| 266804078 | 973 | c71315b9-a731-51db-b9e8-0457565a700c | BALANCE PURIFYING GEL CLEANSER/ 200ml [973] | 2.0000 | 2.0000 | 148200.0000 | 296400.0000 |
| 266811602 | 935 | 36e59086-f4af-5e07-bb4d-42d21bcc9e7b | DAILY MOISTURE SPF PA++++ 50+/ 50ml [935] | 10.0000 | 10.0000 | 151500.0000 | 1515000.0000 |
| 266982666 | 973 | c71315b9-a731-51db-b9e8-0457565a700c | BALANCE PURIFYING GEL CLEANSER/ 200ml [973] | 5.0000 | 5.0000 | 148200.0000 | 741000.0000 |

## Currency Mapping

| source_code | canonical_currency | record_count |
| --- | --- | --- |
| 860 | UZS | 678 |

## Provenance Samples

### Orders

| canonical_id | source_external_id | source_raw_record_id | endpoint | organization | request_filial_id | response_filial_id | trust_classification | raw_external_id |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1fd0969b-90ea-5af5-9da7-c026918bbfbf | 266781320 | b1c11058-db27-5ce4-94d0-eb12535b880a | /b/trade/txs/tdeal/order$export | MODAILY | None | None | CONSISTENT | 266781320 |
| 39ccc4c8-4888-5f78-b31e-636d83161e72 | 266784100 | d377209d-2e8d-5f62-ab55-09c5b283e783 | /b/trade/txs/tdeal/order$export | MODAILY | None | None | CONSISTENT | 266784100 |
| 2851a691-6051-57af-a05f-d95a0f6a1cc7 | 266802977 | 34619624-dff4-54c5-acba-2da0dd21868b | /b/trade/txs/tdeal/order$export | MODAILY | None | None | CONSISTENT | 266802977 |
| 8d42ee40-62d5-56cb-afec-fb502387b115 | 266804078 | 312ba498-1eba-5015-9e6a-f57b9b4b6b7c | /b/trade/txs/tdeal/order$export | MODAILY | None | None | CONSISTENT | 266804078 |
| ce2e89dd-3ecd-500d-b02d-4a11604d4f6c | 266811602 | 8dc3a9d2-a95d-5fcd-a1b0-6dd30fa9f7af | /b/trade/txs/tdeal/order$export | MODAILY | None | None | CONSISTENT | 266811602 |
| b631e4c0-9061-551c-baee-bebd6a997259 | 266982666 | abba8ee4-e3c0-5b70-91fd-4efdc7ba12da | /b/trade/txs/tdeal/order$export | MODAILY | None | None | CONSISTENT | 266982666 |
| 44c85cb1-fc8a-5ab6-b8fa-8bccc19c3798 | 267049912 | 9c14f7fb-9eb0-5c73-8e16-9dcfc311d5ee | /b/trade/txs/tdeal/order$export | MODAILY | None | None | CONSISTENT | 267049912 |
| f0d7a379-ffd0-5eaa-9e28-1eff00d2108c | 266964237 | b2ec1665-b644-5b9a-a430-2b63f1c42a75 | /b/trade/txs/tdeal/order$export | MODAILY | None | None | CONSISTENT | 266964237 |
| 8981ad4a-0d51-5cd0-955a-6b29062ff67d | 266896277 | abdae245-6459-545f-adde-76b16d6741e4 | /b/trade/txs/tdeal/order$export | MODAILY | None | None | CONSISTENT | 266896277 |
| eff55b4e-d3e6-59f2-8a3e-4eeee2e51c7f | 267049916 | fc63dbaa-006c-5345-b2fd-7df97c3b555a | /b/trade/txs/tdeal/order$export | MODAILY | None | None | CONSISTENT | 267049916 |

### Sales

| canonical_id | source_external_id | source_raw_record_id | endpoint | organization | request_filial_id | response_filial_id | trust_classification | raw_external_id |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2dd8d01d-fc9b-5404-ab30-cecc0d726395 | 266781320 | b1c11058-db27-5ce4-94d0-eb12535b880a | /b/trade/txs/tdeal/order$export | MODAILY | None | None | CONSISTENT | 266781320 |
| ad464145-66e9-5fdf-b201-77fc3fec57e6 | 266784100 | d377209d-2e8d-5f62-ab55-09c5b283e783 | /b/trade/txs/tdeal/order$export | MODAILY | None | None | CONSISTENT | 266784100 |
| 1e82021a-558e-5e1d-8c0a-ffb66906ce7e | 266802977 | 34619624-dff4-54c5-acba-2da0dd21868b | /b/trade/txs/tdeal/order$export | MODAILY | None | None | CONSISTENT | 266802977 |
| 2abf2140-e488-5b53-9e91-7c7d3408119a | 266804078 | 312ba498-1eba-5015-9e6a-f57b9b4b6b7c | /b/trade/txs/tdeal/order$export | MODAILY | None | None | CONSISTENT | 266804078 |
| c53d67a9-e563-50fb-8e76-9ef6cceec053 | 266811602 | 8dc3a9d2-a95d-5fcd-a1b0-6dd30fa9f7af | /b/trade/txs/tdeal/order$export | MODAILY | None | None | CONSISTENT | 266811602 |
| 8a87f366-45e6-5f06-9255-9ba53aa09118 | 266982666 | abba8ee4-e3c0-5b70-91fd-4efdc7ba12da | /b/trade/txs/tdeal/order$export | MODAILY | None | None | CONSISTENT | 266982666 |
| cfffdb2d-eb0e-5d57-b1da-8ae1beae8720 | 267049912 | 9c14f7fb-9eb0-5c73-8e16-9dcfc311d5ee | /b/trade/txs/tdeal/order$export | MODAILY | None | None | CONSISTENT | 267049912 |
| e7afa07e-e79d-55d4-a1a1-384de72b902e | 266964237 | b2ec1665-b644-5b9a-a430-2b63f1c42a75 | /b/trade/txs/tdeal/order$export | MODAILY | None | None | CONSISTENT | 266964237 |
| 393d7397-134f-5d8b-8d69-dc02da67496a | 266896277 | abdae245-6459-545f-adde-76b16d6741e4 | /b/trade/txs/tdeal/order$export | MODAILY | None | None | CONSISTENT | 266896277 |
| bfa75b4b-55c0-54eb-911e-d1acf4174e93 | 267049916 | fc63dbaa-006c-5345-b2fd-7df97c3b555a | /b/trade/txs/tdeal/order$export | MODAILY | None | None | CONSISTENT | 267049916 |

### Sale Items

| canonical_id | source_external_id | source_raw_record_id | endpoint | organization | request_filial_id | response_filial_id | trust_classification | raw_external_id |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| aefa2a9b-05eb-57db-a57d-90344c4e3377 | 266776845:1 | 0d585525-fc34-5bd0-9dd0-d4c208d0a46c | /b/trade/txs/tdeal/order$export | MODAILY | None | None | CONSISTENT | 266776845 |
| 3743c1ec-8b70-5ea6-a76c-e00250de925c | 266776845:2 | 0d585525-fc34-5bd0-9dd0-d4c208d0a46c | /b/trade/txs/tdeal/order$export | MODAILY | None | None | CONSISTENT | 266776845 |
| bd152f1e-9613-5506-9956-f8d78cf1bae4 | 266776845:3 | 0d585525-fc34-5bd0-9dd0-d4c208d0a46c | /b/trade/txs/tdeal/order$export | MODAILY | None | None | CONSISTENT | 266776845 |
| 3596b348-6940-53b1-8bbb-b00bcec291b5 | 266776845:4 | 0d585525-fc34-5bd0-9dd0-d4c208d0a46c | /b/trade/txs/tdeal/order$export | MODAILY | None | None | CONSISTENT | 266776845 |
| 29400407-f746-5b21-aa45-875c6dee5608 | 266776845:5 | 0d585525-fc34-5bd0-9dd0-d4c208d0a46c | /b/trade/txs/tdeal/order$export | MODAILY | None | None | CONSISTENT | 266776845 |
| 7ae8db19-ad4e-5155-ad33-ea189ee78d61 | 266776845:6 | 0d585525-fc34-5bd0-9dd0-d4c208d0a46c | /b/trade/txs/tdeal/order$export | MODAILY | None | None | CONSISTENT | 266776845 |
| c3119340-56e9-582d-b93a-1a7f88007937 | 266776845:7 | 0d585525-fc34-5bd0-9dd0-d4c208d0a46c | /b/trade/txs/tdeal/order$export | MODAILY | None | None | CONSISTENT | 266776845 |
| ec9349c4-3cc2-511f-9a5c-8b5f1f1822fb | 266776845:8 | 0d585525-fc34-5bd0-9dd0-d4c208d0a46c | /b/trade/txs/tdeal/order$export | MODAILY | None | None | CONSISTENT | 266776845 |
| 6275bc2b-8100-512c-ad38-1420b8092d7a | 266780917:1 | b54dd918-b3eb-5bc7-8009-f7717bf13e7e | /b/trade/txs/tdeal/order$export | MODAILY | None | None | CONSISTENT | 266780917 |
| 591df443-0c85-5f3a-a038-217f8ead9481 | 266781320:1 | b1c11058-db27-5ce4-94d0-eb12535b880a | /b/trade/txs/tdeal/order$export | MODAILY | None | None | CONSISTENT | 266781320 |
| 2545755d-1706-5d8e-b1e6-d447349a69cb | 266781320:2 | b1c11058-db27-5ce4-94d0-eb12535b880a | /b/trade/txs/tdeal/order$export | MODAILY | None | None | CONSISTENT | 266781320 |
| 2e21ff89-df03-5917-8984-15251376d5e6 | 266784100:1 | d377209d-2e8d-5f62-ab55-09c5b283e783 | /b/trade/txs/tdeal/order$export | MODAILY | None | None | CONSISTENT | 266784100 |
| 13b19d2c-e1a2-5a82-9119-8b896a9394f4 | 266784100:2 | d377209d-2e8d-5f62-ab55-09c5b283e783 | /b/trade/txs/tdeal/order$export | MODAILY | None | None | CONSISTENT | 266784100 |
| e3060031-bdcc-588e-aa94-fef0aaab9a4c | 266784100:3 | d377209d-2e8d-5f62-ab55-09c5b283e783 | /b/trade/txs/tdeal/order$export | MODAILY | None | None | CONSISTENT | 266784100 |
| 3a50aa21-d83d-525f-8b53-ca4398742b77 | 266784100:4 | d377209d-2e8d-5f62-ab55-09c5b283e783 | /b/trade/txs/tdeal/order$export | MODAILY | None | None | CONSISTENT | 266784100 |
| bce7e15c-d60c-5c2e-979c-f4676fdd506b | 266802977:1 | 34619624-dff4-54c5-acba-2da0dd21868b | /b/trade/txs/tdeal/order$export | MODAILY | None | None | CONSISTENT | 266802977 |
| fa577aac-fac1-59e4-8252-3811ca43f24d | 266802977:2 | 34619624-dff4-54c5-acba-2da0dd21868b | /b/trade/txs/tdeal/order$export | MODAILY | None | None | CONSISTENT | 266802977 |
| 8438e7f0-50c0-5f16-b9e2-1881b5dc4651 | 266802977:3 | 34619624-dff4-54c5-acba-2da0dd21868b | /b/trade/txs/tdeal/order$export | MODAILY | None | None | CONSISTENT | 266802977 |
| 7d574b37-eb9d-5926-aca8-1446f9a0e996 | 266802977:4 | 34619624-dff4-54c5-acba-2da0dd21868b | /b/trade/txs/tdeal/order$export | MODAILY | None | None | CONSISTENT | 266802977 |
| a49c1ae4-3c22-52b3-b5e5-fb3c28a1a8a7 | 266802977:5 | 34619624-dff4-54c5-acba-2da0dd21868b | /b/trade/txs/tdeal/order$export | MODAILY | None | None | CONSISTENT | 266802977 |

## Data Quality

| table | VERIFIED | PARTIAL | UNRESOLVED | UNSAFE |
| --- | --- | --- | --- | --- |
| canonical_orders | 107 | 0 | 0 | 0 |
| canonical_sales | 100 | 0 | 0 | 0 |
| canonical_sale_items | 471 | 0 | 0 | 0 |

## Revenue Preview

Canonical V2 Revenue (VERIFIED canonical_sales): **318557570.0000 UZS**
Sales count: **100**
Sold units: **1975.0000**

| organization | revenue | sales_count | sold_units |
| --- | --- | --- | --- |
| Администрация | 0 | 0 | 0 |
| MODAILY | 292902270.0000 | 88 | 1737.0000 |
| MODAILY ANDIJON | 0 | 0 | 0 |
| MODAILY NAMANGAN | 0 | 0 | 0 |
| MODAILY QOQON VA FARGONA | 20138300.0000 | 10 | 111.0000 |
| MODAILY SURXANDARYO | 0 | 0 | 0 |
| SAMO SERVIS | 5517000.0000 | 2 | 127.0000 |

Old Revenue: **432419140 UZS**
Difference: **-113861570.0000 UZS**

## Sales Detail Test

### MODAILY · 266781320

- Date: `None`
- Customer: `SAYFULLAYEVA MUXLISA SHUKURILLA QIZI`
- Status: `approved`
- Currency: `UZS`
- Order amount: `1188000.0000`
- Realized sale: `True`
- Why: `sold_quant`
- Products:
  - BALANCING FOAM CLEANSER/ 150ml [966] | ordered=3.0000 sold=3.0000 returned=0.0000 unit_price=143500.0000 amount=430500.0000
  - DAILY MOISTURE SPF PA++++ 50+/ 50ml [935] | ordered=5.0000 sold=5.0000 returned=0.0000 unit_price=151500.0000 amount=757500.0000

### MODAILY · 266784100

- Date: `None`
- Customer: `MUXAMMEDOVA SABINA AVAZ QIZI`
- Status: `approved`
- Currency: `UZS`
- Order amount: `764600.0000`
- Realized sale: `True`
- Why: `sold_quant`
- Products:
  - BALANCE PURIFYING GEL CLEANSER/ 200ml [973] | ordered=1.0000 sold=1.0000 returned=0.0000 unit_price=148200.0000 amount=148200.0000
  - ELASTIC GLOW PERFECTING TONER/ 100ml [000] | ordered=1.0000 sold=1.0000 returned=0.0000 unit_price=129700.0000 amount=129700.0000
  - REFINE & RENEW B3 SERUM/ 30ml [959] | ordered=1.0000 sold=1.0000 returned=0.0000 unit_price=229600.0000 amount=229600.0000
  - RETINAGE FIRMING SERUM/ 30ml [942] | ordered=1.0000 sold=1.0000 returned=0.0000 unit_price=257100.0000 amount=257100.0000

### MODAILY · 266802977

- Date: `None`
- Customer: `UNIVERSAL-FARM-PLUS МЧЖ`
- Status: `unmapped`
- Currency: `UZS`
- Order amount: `22995600.0000`
- Realized sale: `True`
- Why: `sold_quant`
- Products:
  - BALANCE PURIFYING GEL CLEANSER/ 200ml [973] | ordered=12.0000 sold=12.0000 returned=0.0000 unit_price=148200.0000 amount=1778400.0000
  - BALANCING FOAM CLEANSER/ 150ml [966] | ordered=12.0000 sold=12.0000 returned=0.0000 unit_price=143500.0000 amount=1722000.0000
  - DAILY GLOW HYDRATING CREAM/ 50ml [904] | ordered=12.0000 sold=12.0000 returned=0.0000 unit_price=192400.0000 amount=2308800.0000
  - DAILY MOISTURE SPF PA++++ 50+/ 50ml [935] | ordered=12.0000 sold=12.0000 returned=0.0000 unit_price=151500.0000 amount=1818000.0000
  - ELASTIC GLOW PERFECTING TONER/ 100ml [000] | ordered=12.0000 sold=12.0000 returned=0.0000 unit_price=129700.0000 amount=1556400.0000
  - NIGHT RECOVERY CREAM/ 50ml [911] | ordered=12.0000 sold=12.0000 returned=0.0000 unit_price=217800.0000 amount=2613600.0000
  - ONSEN THERAPY MIST/ 120ml [997] | ordered=12.0000 sold=12.0000 returned=0.0000 unit_price=154500.0000 amount=1854000.0000
  - REFINE & RENEW B3 SERUM/ 30ml [959] | ordered=12.0000 sold=12.0000 returned=0.0000 unit_price=229600.0000 amount=2755200.0000
  - RETINAGE FIRMING SERUM/ 30ml [942] | ordered=12.0000 sold=12.0000 returned=0.0000 unit_price=257100.0000 amount=3085200.0000
  - SILK TOUCH HAND CREAM/ 80ml [980] | ordered=12.0000 sold=12.0000 returned=0.0000 unit_price=72700.0000 amount=872400.0000
  - SKIN LIFTING COLLAGEN CREAM/ 50ml [928] | ordered=12.0000 sold=12.0000 returned=0.0000 unit_price=219300.0000 amount=2631600.0000

### MODAILY · 266804078

- Date: `None`
- Customer: `Shodiyova Asaloy Asqar qizi`
- Status: `approved`
- Currency: `UZS`
- Order amount: `296400.0000`
- Realized sale: `True`
- Why: `sold_quant`
- Products:
  - BALANCE PURIFYING GEL CLEANSER/ 200ml [973] | ordered=2.0000 sold=2.0000 returned=0.0000 unit_price=148200.0000 amount=296400.0000

### MODAILY · 266811602

- Date: `None`
- Customer: `ЧП "SOLIHA QUDDUS" O'RIKZOR 1-18 подвал`
- Status: `approved`
- Currency: `UZS`
- Order amount: `1515000.0000`
- Realized sale: `True`
- Why: `sold_quant`
- Products:
  - DAILY MOISTURE SPF PA++++ 50+/ 50ml [935] | ordered=10.0000 sold=10.0000 returned=0.0000 unit_price=151500.0000 amount=1515000.0000

### MODAILY · 266982666

- Date: `None`
- Customer: `MADINAPA KENAYE`
- Status: `approved`
- Currency: `UZS`
- Order amount: `7688000.0000`
- Realized sale: `True`
- Why: `sold_quant`
- Products:
  - BALANCE PURIFYING GEL CLEANSER/ 200ml [973] | ordered=5.0000 sold=5.0000 returned=0.0000 unit_price=148200.0000 amount=741000.0000
  - DAILY GLOW HYDRATING CREAM/ 50ml [904] | ordered=5.0000 sold=5.0000 returned=0.0000 unit_price=192400.0000 amount=962000.0000
  - NIGHT RECOVERY CREAM/ 50ml [911] | ordered=5.0000 sold=5.0000 returned=0.0000 unit_price=217800.0000 amount=1089000.0000
  - SKIN LIFTING COLLAGEN CREAM/ 50ml [928] | ordered=5.0000 sold=5.0000 returned=0.0000 unit_price=219300.0000 amount=1096500.0000
  - BALANCING FOAM CLEANSER/ 150ml [966] | ordered=5.0000 sold=5.0000 returned=0.0000 unit_price=143500.0000 amount=717500.0000
  - ELASTIC GLOW PERFECTING TONER/ 100ml [000] | ordered=5.0000 sold=5.0000 returned=0.0000 unit_price=129700.0000 amount=648500.0000
  - REFINE & RENEW B3 SERUM/ 30ml [959] | ordered=5.0000 sold=5.0000 returned=0.0000 unit_price=229600.0000 amount=1148000.0000
  - RETINAGE FIRMING SERUM/ 30ml [942] | ordered=5.0000 sold=5.0000 returned=0.0000 unit_price=257100.0000 amount=1285500.0000

### MODAILY · 267049912

- Date: `None`
- Customer: `ROZIKOVA MAXLIYO AZAMATOVNA`
- Status: `approved`
- Currency: `UZS`
- Order amount: `576200.0000`
- Realized sale: `True`
- Why: `sold_quant`
- Products:
  - BALANCING FOAM CLEANSER/ 150ml [966] | ordered=1.0000 sold=1.0000 returned=0.0000 unit_price=143500.0000 amount=143500.0000
  - ELASTIC GLOW PERFECTING TONER/ 100ml [000] | ordered=1.0000 sold=1.0000 returned=0.0000 unit_price=129700.0000 amount=129700.0000
  - DAILY MOISTURE SPF PA++++ 50+/ 50ml [935] | ordered=2.0000 sold=2.0000 returned=0.0000 unit_price=151500.0000 amount=303000.0000

### MODAILY · 266964237

- Date: `None`
- Customer: `AXMETOVA MOHINUR`
- Status: `approved`
- Currency: `UZS`
- Order amount: `1916300.0000`
- Realized sale: `True`
- Why: `sold_quant`
- Products:
  - SKIN LIFTING COLLAGEN CREAM/ 50ml [928] | ordered=1.0000 sold=1.0000 returned=0.0000 unit_price=219300.0000 amount=219300.0000
  - RETINAGE FIRMING SERUM/ 30ml [942] | ordered=1.0000 sold=1.0000 returned=0.0000 unit_price=257100.0000 amount=257100.0000
  - SILK TOUCH HAND CREAM/ 80ml [980] | ordered=1.0000 sold=1.0000 returned=0.0000 unit_price=72700.0000 amount=72700.0000
  - ONSEN THERAPY MIST/ 120ml [997] | ordered=1.0000 sold=1.0000 returned=0.0000 unit_price=154500.0000 amount=154500.0000
  - REFINE & RENEW B3 SERUM/ 30ml [959] | ordered=1.0000 sold=1.0000 returned=0.0000 unit_price=229600.0000 amount=229600.0000
  - ELASTIC GLOW PERFECTING TONER/ 100ml [000] | ordered=1.0000 sold=1.0000 returned=0.0000 unit_price=129700.0000 amount=129700.0000
  - NIGHT RECOVERY CREAM/ 50ml [911] | ordered=1.0000 sold=1.0000 returned=0.0000 unit_price=217800.0000 amount=217800.0000
  - DAILY GLOW HYDRATING CREAM/ 50ml [904] | ordered=1.0000 sold=1.0000 returned=0.0000 unit_price=192400.0000 amount=192400.0000
  - DAILY MOISTURE SPF PA++++ 50+/ 50ml [935] | ordered=1.0000 sold=1.0000 returned=0.0000 unit_price=151500.0000 amount=151500.0000
  - BALANCE PURIFYING GEL CLEANSER/ 200ml [973] | ordered=1.0000 sold=1.0000 returned=0.0000 unit_price=148200.0000 amount=148200.0000
  - BALANCING FOAM CLEANSER/ 150ml [966] | ordered=1.0000 sold=1.0000 returned=0.0000 unit_price=143500.0000 amount=143500.0000

### MODAILY · 266896277

- Date: `None`
- Customer: `ELOV ASQAR KAMOLOVICH 6-10`
- Status: `approved`
- Currency: `UZS`
- Order amount: `4625000.0000`
- Realized sale: `True`
- Why: `sold_quant`
- Products:
  - DAILY MOISTURE SPF PA++++ 50+/ 50ml [935] | ordered=6.0000 sold=6.0000 returned=0.0000 unit_price=151500.0000 amount=909000.0000
  - REFINE & RENEW B3 SERUM/ 30ml [959] | ordered=3.0000 sold=3.0000 returned=0.0000 unit_price=229600.0000 amount=688800.0000
  - RETINAGE FIRMING SERUM/ 30ml [942] | ordered=3.0000 sold=3.0000 returned=0.0000 unit_price=257100.0000 amount=771300.0000
  - ONSEN THERAPY MIST/ 120ml [997] | ordered=3.0000 sold=3.0000 returned=0.0000 unit_price=154500.0000 amount=463500.0000
  - ELASTIC GLOW PERFECTING TONER/ 100ml [000] | ordered=2.0000 sold=2.0000 returned=0.0000 unit_price=129700.0000 amount=259400.0000
  - BALANCE PURIFYING GEL CLEANSER/ 200ml [973] | ordered=3.0000 sold=3.0000 returned=0.0000 unit_price=148200.0000 amount=444600.0000
  - BALANCING FOAM CLEANSER/ 150ml [966] | ordered=3.0000 sold=3.0000 returned=0.0000 unit_price=143500.0000 amount=430500.0000
  - SKIN LIFTING COLLAGEN CREAM/ 50ml [928] | ordered=3.0000 sold=3.0000 returned=0.0000 unit_price=219300.0000 amount=657900.0000

### MODAILY · 267049916

- Date: `None`
- Customer: `Miss ledi parfyumerya kosmetika _ 116 dòkon.`
- Status: `approved`
- Currency: `UZS`
- Order amount: `367500.0000`
- Realized sale: `True`
- Why: `sold_quant`
- Products:
  - BALANCE PURIFYING GEL CLEANSER/ 200ml [973] | ordered=1.0000 sold=1.0000 returned=0.0000 unit_price=148200.0000 amount=148200.0000
  - SKIN LIFTING COLLAGEN CREAM/ 50ml [928] | ordered=1.0000 sold=1.0000 returned=0.0000 unit_price=219300.0000 amount=219300.0000

## Final Report

RAW trusted orders: **110**
RAW unsafe orders: **107**

Canonical orders: **107**
Canonical sales: **100**
Canonical sale items: **471**

Organization isolation: **PASS**
Idempotency: **PASS**
Provenance: **PASS**
Customer linkage: **100.00%**
Product linkage: **100.00%**
Quantity reconciliation: **PASS**
Money reconciliation: **PASS**
Unsafe exclusion: **PASS**
Canonical V2 Revenue: **318557570.0000 UZS**
Old Revenue: **432419140 UZS**
Difference: **-113861570.0000 UZS**
Reason: `V2 currently counts only VERIFIED realized canonical_sales from trusted SmartUp order RAW; old KPI came from legacy revenue logic and broader historical scope.`
REALIZATION RULE: `canonical_sales создаются только если в order row есть explicit realization evidence: сначала сумма details[].sold_quant > 0, иначе любой positive line sold_amount/amount > 0. Сам source status сам по себе sale не создаёт.`

### CRITICAL ISSUES

- None

PHASE 2A: **PASS**
READY FOR PHASE 2B: **YES**
