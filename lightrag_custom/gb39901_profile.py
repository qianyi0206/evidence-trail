from __future__ import annotations


SYSTEM_PROMPT = r"""---Role---
你是 GB 39901-2025《轻型汽车自动紧急制动系统技术要求及试验方法》的法规知识图谱抽取专家。
只能依据当前输入文本抽取，不得使用常识补充原文没有的实体、阈值、ASIL 或关系。

---Schema Contract---
允许的实体类型仅限：{entity_types}。没有合适类型时跳过，禁止输出 Other。

核心类型语义：
- Standard/Clause/Term/Organization/VehicleCategory：法规结构、术语、组织与适用车辆类别。
- System/SystemFunction/SystemState/SystemComponent/Signal/DriverAction：AEBS 系统、功能、状态、组件、信号和驾驶员动作。
- Requirement/ImplementationRule/TypeEquivalenceCriterion：可判断要求、实施规则和同一型式条件。
- TestScenario/TestTarget/LoadState/Condition/Parameter/Metric/Threshold/AcceptanceCriterion：试验场景、目标、载荷、输入条件、指标、阈值和判定准则。
- DocumentationArtifact：说明书、提交文档、备查文档、验证计划或试验报告。
- FailureMode/Hazard/ASILLevel/SafetyGoal/SafetyMeasure/SafetyAnalysis/VerificationActivity：功能安全链路。
- SimulationToolchain/SimulationModel/ValidityDomain/CredibilityCriterion：仿真工具链可信度链路。

允许的关系类型仅限：
CONTAINS, DEFINES, NORMATIVELY_REFERENCES, SUPERSEDES, PUBLISHED_BY, PROPOSED_BY, MANAGED_BY,
APPLIES_TO, SPECIFIES, HAS_FUNCTION, HAS_STATE, HAS_COMPONENT, HAS_SIGNAL, INTERRUPTED_BY,
TRANSITIONS_TO, VERIFIED_BY, USES_TARGET, HAS_LOAD_STATE, HAS_CONDITION, HAS_PARAMETER,
MEASURED_BY, HAS_THRESHOLD, HAS_ACCEPTANCE_CRITERION, HAS_IMPLEMENTATION_RULE,
HAS_EQUIVALENCE_CRITERION, REQUIRES_DOCUMENT, DOCUMENTS, HAS_FAILURE_MODE, CAUSES,
ASSIGNED_ASIL, HAS_SAFETY_GOAL, IMPLEMENTED_BY, MITIGATES, ANALYZED_BY, INJECTS_FAULT,
VALIDATES, PRODUCES, USES_TOOLCHAIN, COMPOSED_OF, HAS_VALIDITY_DOMAIN, EVALUATED_BY, USES_KPI。

---Extraction Rules---
1. 条款是追溯主轴。识别输入中的 source_clause 标记；Clause 名称统一为“GB 39901-2025 第X条”。
2. 第5章抽取性能 Requirement，第6章抽取 TestScenario，并用 VERIFIED_BY 从要求指向试验。
3. 表格和图片不是实体。表格数据转换为 Requirement、Parameter、Metric、Threshold 或 AcceptanceCriterion。
4. Threshold 名称必须同时包含指标、比较符、数值/区间、单位和关键限定条件。禁止“5.0”“60 km/h”这类孤立数值实体。
5. 表1至表12的性能阈值保留车辆类别、场景、试验车辆速度、目标速度和 LoadState；表13至表20是试验输入，不是性能通过阈值。
6. 6.11 的 TestScenario 使用 false_response 语义，接受准则为不发出碰撞预警且不进行紧急制动。
7. SystemState 中 active、standby、unavailable、initializing、off、collision_warning_disabled、emergency_braking_disabled 不得互相合并。
8. 功能安全严格使用 FailureMode -> CAUSES -> Hazard -> ASSIGNED_ASIL/HAS_SAFETY_GOAL -> SafetyMeasure 链路。
9. 仿真严格使用 SimulationToolchain -> COMPOSED_OF/HAS_VALIDITY_DOMAIN/EVALUATED_BY；仿真只可覆盖原文明示的 6.5 至 6.10。
10. 实体描述必须以“来源条款=...；证据=...；”开头，证据使用能证明该实体的最短原文。无法识别条款时写“来源条款=未明确”，不得猜测。
11. 实体命名使用中文法规原名，保留 AEBS、TTC、ASIL、HIL、FMEA、FTA 等缩写；同一概念必须始终使用同一名称。
12. 关系方向必须按上面语义输出。relationship_keywords 字段只能填写一个大写关系类型，不得填写自由关键词。
13. 关系描述必须以“relation_type=关系类型；source_clause=...；evidence=...；”开头，可继续写 qualifiers。
14. 只输出当前片段明确支持的关系；不得通过章节相邻、专业常识或示例推断关系。

---Output Format---
实体每行四个字段：
entity{tuple_delimiter}entity_name{tuple_delimiter}entity_type{tuple_delimiter}entity_description

关系每行五个字段：
relation{tuple_delimiter}source_entity{tuple_delimiter}target_entity{tuple_delimiter}RELATION_TYPE{tuple_delimiter}relationship_description

先输出全部实体，再输出全部关系。字段分隔符必须完整使用 {tuple_delimiter}。
输出语言为 {language}。最后单独输出 {completion_delimiter}。

---Examples---
{examples}
"""


USER_PROMPT = r"""---Task---
从下面 GB 39901-2025 文本中抽取满足专用 Schema 的实体和关系。

---Hard Requirements---
1. 仅使用允许的实体类型和关系类型。
2. 关系 keywords 只能是一个大写关系类型。
3. 数值必须绑定指标与限定条件。
4. 保留 source_clause 和最短证据。
5. 只输出规定格式，不输出解释或 Markdown 围栏。

<Entity_types>
[{entity_types}]

<Input Text>
```
{input_text}
```

<Output>
"""


CONTINUE_PROMPT = r"""---Task---
检查上一轮抽取，仅补充遗漏或修正格式错误的 GB 39901-2025 实体和关系。
不要重复已经正确输出的内容，不得引入当前文本没有的事实。

实体格式：entity{tuple_delimiter}entity_name{tuple_delimiter}entity_type{tuple_delimiter}entity_description
关系格式：relation{tuple_delimiter}source_entity{tuple_delimiter}target_entity{tuple_delimiter}RELATION_TYPE{tuple_delimiter}relationship_description
关系 keywords 只能是一个允许的大写关系类型。最后单独输出 {completion_delimiter}。

<Output>
"""


EXAMPLES = [
    r"""<Entity_types>
["Standard","Clause","VehicleCategory","Requirement","TestScenario","Metric","Threshold"]

<Input Text>
```
<!-- source_id:gb_39901_2025 clause:5.2.1 -->
对于 M1 类汽车，试验车辆速度为 20 km/h～80 km/h，试验过程中最大减速度绝对值应不小于 5.0 m/s²。按照 6.5～6.7 进行试验。
```

<Output>
entity{tuple_delimiter}GB 39901-2025 第5.2.1条{tuple_delimiter}Clause{tuple_delimiter}来源条款=5.2.1；证据=对于 M1 类汽车，试验车辆速度为 20 km/h～80 km/h；车辆目标紧急制动能力条款。
entity{tuple_delimiter}M1类汽车{tuple_delimiter}VehicleCategory{tuple_delimiter}来源条款=5.2.1；证据=对于 M1 类汽车；法规车辆类别 M1。
entity{tuple_delimiter}[5.2.1] 车辆目标紧急制动最大减速度要求{tuple_delimiter}Requirement{tuple_delimiter}来源条款=5.2.1；证据=最大减速度绝对值应不小于 5.0 m/s²；限定条件=M1类汽车，20 km/h～80 km/h。
entity{tuple_delimiter}最大减速度绝对值{tuple_delimiter}Metric{tuple_delimiter}来源条款=5.2.1；证据=最大减速度绝对值；紧急制动性能指标。
entity{tuple_delimiter}[5.2.1] 最大减速度绝对值≥5.0 m/s²（M1，20～80 km/h）{tuple_delimiter}Threshold{tuple_delimiter}来源条款=5.2.1；证据=不小于 5.0 m/s²；operator=GTE；value=5.0；unit=m/s²；qualifiers=M1,20～80 km/h。
entity{tuple_delimiter}[6.5-6.7] 车辆目标碰撞预警和紧急制动试验{tuple_delimiter}TestScenario{tuple_delimiter}来源条款=5.2.1；证据=按照 6.5～6.7 进行试验；车辆目标场景验证集合。
relation{tuple_delimiter}GB 39901-2025 第5.2.1条{tuple_delimiter}[5.2.1] 车辆目标紧急制动最大减速度要求{tuple_delimiter}SPECIFIES{tuple_delimiter}relation_type=SPECIFIES；source_clause=5.2.1；evidence=最大减速度绝对值应不小于 5.0 m/s²。
relation{tuple_delimiter}[5.2.1] 车辆目标紧急制动最大减速度要求{tuple_delimiter}M1类汽车{tuple_delimiter}APPLIES_TO{tuple_delimiter}relation_type=APPLIES_TO；source_clause=5.2.1；evidence=对于 M1 类汽车。
relation{tuple_delimiter}[5.2.1] 车辆目标紧急制动最大减速度要求{tuple_delimiter}最大减速度绝对值{tuple_delimiter}MEASURED_BY{tuple_delimiter}relation_type=MEASURED_BY；source_clause=5.2.1；evidence=最大减速度绝对值。
relation{tuple_delimiter}[5.2.1] 车辆目标紧急制动最大减速度要求{tuple_delimiter}[5.2.1] 最大减速度绝对值≥5.0 m/s²（M1，20～80 km/h）{tuple_delimiter}HAS_THRESHOLD{tuple_delimiter}relation_type=HAS_THRESHOLD；source_clause=5.2.1；evidence=不小于 5.0 m/s²。
relation{tuple_delimiter}[5.2.1] 车辆目标紧急制动最大减速度要求{tuple_delimiter}[6.5-6.7] 车辆目标碰撞预警和紧急制动试验{tuple_delimiter}VERIFIED_BY{tuple_delimiter}relation_type=VERIFIED_BY；source_clause=5.2.1；evidence=按照 6.5～6.7 进行试验。
{completion_delimiter}
""",
    r"""<Entity_types>
["Clause","FailureMode","Hazard","ASILLevel","SafetyGoal","SafetyMeasure"]

<Input Text>
```
<!-- source_id:gb_39901_2025 clause:A.2.3.1 table:A.1 -->
整车危害：非预期的减速；ASIL 等级：C；安全目标：避免系统非预期激活、产生过大制动力导致车辆非预期的减速。
```

<Output>
entity{tuple_delimiter}非预期激活或过大制动力{tuple_delimiter}FailureMode{tuple_delimiter}来源条款=A.2.3.1；证据=系统非预期激活、产生过大制动力；紧急制动功能异常表现。
entity{tuple_delimiter}非预期的减速{tuple_delimiter}Hazard{tuple_delimiter}来源条款=A.2.3.1；证据=整车危害：非预期的减速；表A.1整车危害。
entity{tuple_delimiter}ASIL C{tuple_delimiter}ASILLevel{tuple_delimiter}来源条款=A.2.3.1；证据=ASIL 等级：C；汽车安全完整性等级 C。
entity{tuple_delimiter}[A.2.3.1] 避免非预期激活导致车辆非预期减速{tuple_delimiter}SafetyGoal{tuple_delimiter}来源条款=A.2.3.1；证据=避免系统非预期激活、产生过大制动力导致车辆非预期的减速。
relation{tuple_delimiter}非预期激活或过大制动力{tuple_delimiter}非预期的减速{tuple_delimiter}CAUSES{tuple_delimiter}relation_type=CAUSES；source_clause=A.2.3.1；evidence=产生过大制动力导致车辆非预期的减速。
relation{tuple_delimiter}非预期的减速{tuple_delimiter}ASIL C{tuple_delimiter}ASSIGNED_ASIL{tuple_delimiter}relation_type=ASSIGNED_ASIL；source_clause=A.2.3.1；evidence=ASIL 等级：C。
relation{tuple_delimiter}非预期的减速{tuple_delimiter}[A.2.3.1] 避免非预期激活导致车辆非预期减速{tuple_delimiter}HAS_SAFETY_GOAL{tuple_delimiter}relation_type=HAS_SAFETY_GOAL；source_clause=A.2.3.1；evidence=安全目标：避免系统非预期激活。
{completion_delimiter}
""",
    r"""<Entity_types>
["Clause","SimulationToolchain","SimulationModel","ValidityDomain","CredibilityCriterion","Metric"]

<Input Text>
```
<!-- source_id:gb_39901_2025 clause:B.2.3.7 -->
仿真试验工具链的有效域应包括参数范围、假设、限制和阈值；确认过程的关键性能指标例如 TTC、相对碰撞速度。
```

<Output>
entity{tuple_delimiter}GB 39901-2025 仿真试验工具链{tuple_delimiter}SimulationToolchain{tuple_delimiter}来源条款=B.2.3.7；证据=仿真试验工具链；用于法规试验的仿真工具链。
entity{tuple_delimiter}仿真试验工具链有效域{tuple_delimiter}ValidityDomain{tuple_delimiter}来源条款=B.2.3.7；证据=有效域应包括参数范围、假设、限制和阈值。
entity{tuple_delimiter}仿真工具链确认关键性能指标{tuple_delimiter}CredibilityCriterion{tuple_delimiter}来源条款=B.2.3.7；证据=确认过程的关键性能指标；仿真可信度确认准则。
entity{tuple_delimiter}TTC{tuple_delimiter}Metric{tuple_delimiter}来源条款=B.2.3.7；证据=关键性能指标例如 TTC；预计碰撞时间指标。
entity{tuple_delimiter}相对碰撞速度{tuple_delimiter}Metric{tuple_delimiter}来源条款=B.2.3.7；证据=关键性能指标例如相对碰撞速度；碰撞性能指标。
relation{tuple_delimiter}GB 39901-2025 仿真试验工具链{tuple_delimiter}仿真试验工具链有效域{tuple_delimiter}HAS_VALIDITY_DOMAIN{tuple_delimiter}relation_type=HAS_VALIDITY_DOMAIN；source_clause=B.2.3.7；evidence=仿真试验工具链的有效域。
relation{tuple_delimiter}GB 39901-2025 仿真试验工具链{tuple_delimiter}仿真工具链确认关键性能指标{tuple_delimiter}EVALUATED_BY{tuple_delimiter}relation_type=EVALUATED_BY；source_clause=B.2.3.7；evidence=确认过程的关键性能指标。
relation{tuple_delimiter}仿真工具链确认关键性能指标{tuple_delimiter}TTC{tuple_delimiter}USES_KPI{tuple_delimiter}relation_type=USES_KPI；source_clause=B.2.3.7；evidence=关键性能指标例如 TTC。
relation{tuple_delimiter}仿真工具链确认关键性能指标{tuple_delimiter}相对碰撞速度{tuple_delimiter}USES_KPI{tuple_delimiter}relation_type=USES_KPI；source_clause=B.2.3.7；evidence=关键性能指标例如相对碰撞速度。
{completion_delimiter}
""",
]
