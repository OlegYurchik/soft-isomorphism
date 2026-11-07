# Трассировка примеров датасетов

Дата аудита: 06.11.2026. Источник строк — локальные FactKG dev pickle и HotpotQA
validation parquet; сырые файлы не коммитируются. Трассировка проверяет поля и путь
до evaluator gold. Она не является запуском extractor или graph matcher.

## FactKG: 10 проверенных строк

Для каждой строки входом runtime является только claim. Label, Entity_set и Evidence
остаются evaluator-only. Evidence задаёт путь/ограничение, а не уникальный список троек.

| id | claim | label | entity set | evidence / type |
|---:|---|---|---|---|
| 0 | His name is W. Haydon Burns, and he had a successor. | True | W._Haydon_Burns | successor / existence |
| 1 | I know that Paul Hitch Roney had a successor to him. | True | Paul_Hitch_Roney | successor / existence |
| 2 | Ocean Software did have a successor. | True | Ocean_Software | successor / existence |
| 3 | Yes, and he had a successor named James F. Price! | True | James_F._Price | successor / existence |
| 4 | I know that Ella Kalsbeek had a successor too. | True | Ella_Kalsbeek | successor / existence |
| 5 | Yes, and Robert K. Hamilton had a successor. | True | Robert_K._Hamilton | successor / existence |
| 6 | He was Ramiro I of Asturias, who had a successor. | True | Ramiro_I_of_Asturias | successor / existence |
| 7 | Yes, Rustam I had a successor as well! | True | Rustam_I | successor / existence |
| 8 | Well, Jan O'Sullivan had a successor after all. | True | Jan_O'Sullivan | successor / existence |
| 9 | Tom Udall actually had a successor when he died. | True | Tom_Udall | successor / existence |

Первые десять строк проверяют схему, но все имеют тип `existence`. Дополнительно
проверены пять строк с другими типами; их устойчивые ID — SHA256 исходного claim:

| SHA256 claim | Тип / Label | Вход → evaluator gold |
|---|---|---|
| `897fcd0915178fd10750375cd2ef4f8db36e953926bfc51a39fa446f10eeb047` | substitution, False | Lesley Griffiths was Edwina Hart's daughter? → Edwina_Hart / children и Lesley_Griffiths / ~children |
| `fb4758831833ae9e1da1525d16679294e0db8b506de952a9d770a7c468ad05dd` | multi claim, False | The capital of Alderney is Saint Anne and they have the Red Oak Municipal Airport. → capital / ~cityServed paths |
| `2acd9b120ff62b4c6fb5ce51fee2fc0aa62ff298ec7cb1195005708587eb7566` | negation, False | Nissan G engine did not have a successor → Nissan_G_engine / successor |
| `95163cecac2f97080ab0c8f0709c1614b18e7e7ad72e56b412587ac12f24f28c` | multi hop, True | Pakistan Civil Aviation Authority governs the airport in Pakistan → Pakistan / ~location,operator |
| `d26e595d7d7a47ee880c3eda3121063997fe2ef6988a841a834add303aeecb4f` | num3 + multi claim, False | Allama Iqbal International Airport runway length 2900 metres → location/runwayLength/runwayDesignation paths |

`~relation` в Evidence обозначает обратный шаг пути. Здесь он сохранён как
аннотация; никакая тройка не реконструируется без DBpedia light.

## HotpotQA: 10 проверенных строк

Для runtime сохраняются question и все 10 contexts. Answer и supporting facts доступны
только evaluator; supporting facts привязаны к `(title, sentence_id)`.

| id | question (сокращённо) | answer | supporting facts |
|---|---|---|---|
| 5a8b57f25542995d1e6f1371 | Scott Derrickson и Ed Wood одной национальности? | yes | Scott Derrickson:0; Ed Wood:0 |
| 5a8c7595554299585d9e36b6 | Какая должность была у актрисы Corliss Archer? | Chief of Protocol | Kiss and Tell:0; Shirley Temple:0,1 |
| 5a85ea095542994775f606a8 | Какая young-adult серия описана в вопросе? | Animorphs | Hork-Bajir Chronicles:0,1,2; Animorphs:0,1 |
| 5adbf0a255429947ff17385a | В одном ли районе Laleli Mosque и Esma Sultan Mansion? | no | Laleli Mosque:0; Esma Sultan Mansion:0 |
| 5a8e3ea95542995a26add48d | В каком районе Нью-Йорка находится режиссёр Big Stone Gap? | Greenwich Village | Big Stone Gap:0; Adriana Trigiani:0 |
| 5abd94525542992ac4f382d2 | Кто сформировал группу, выпустившую 2014 S/S? | YG Entertainment | 2014 S/S:0; Winner:0 |
| 5a85b2d95542997b5ce40028 | Кто известен как Aladin? | Eenasul Fateh | Eenasul Fateh:0; Management consulting:0 |
| 5a87ab905542996e4f3088c1 | Вместимость арены Lewiston Maineiacs? | 3,677 seated | Lewiston Maineiacs:1; Androscoggin Bank Colisée:0 |
| 5a7bbb64554299042af8f7cc | Кто старше: Annie Morton или Terry Richardson? | Terry Richardson | Annie Morton:0,2; Terry Richardson:0 |
| 5a8db19d5542994ba4e3dd00 | Local H и For Against из США? | yes | Local H:0; For Against:0 |

## Оставшийся блокер

Трассировка подтверждает доступность и структуру выбранных файлов. Для полноценного
graph experiment остаются DBpedia light, Qwen runtime и реализация extraction/candidate
generation. Нельзя считать эти 20 строк независимой оценкой метода: они использованы
для проверки формата и должны быть исключены из настройки, если попадут в ручной аудит.

## Воспроизведение проверки

Из корня репозитория с загруженными авторскими файлами: `sha256sum data/factkg/data/factkg_unzip/factkg_{train,dev,test}.pickle data/hotpotqa/validation.parquet`.
Проверка FactKG dev по первым 10 строкам и типам: `python -c 'import pickle,collections; r=pickle.load(open("data/factkg/data/factkg_unzip/factkg_dev.pickle","rb")); print(len(r),list(r.items())[:10]); print(collections.Counter(t for row in r.values() for t in row["types"]))'`.
Проверка HotpotQA: `python -c 'import pandas as pd; p=pd.read_parquet("data/hotpotqa/validation.parquet"); print(len(p),p[["id","question","answer","supporting_facts"]].head(10).to_dict("records"))'`.
Файлы pickle следует брать только из доверенного авторского репозитория.

Оценка оставшейся подготовки: 2–4 часа для загрузки и проверки DBpedia light,
2–4 часа для адаптера KG и проверки направления `~relation`; отдельное время
потребуется на LLM extraction и измерение runtime. Это оценка работы, не результат
ресурсного замера.
