#!/usr/bin/env python3
"""Build the manually curated GB 39901 GraphRAG benchmark artifacts.

This module is deliberately data-oriented.  Every question, claim, evidence
binding, and reasoning step is explicitly listed below; code only materializes
the records and makes repeated mechanical fields consistent.
"""

from __future__ import annotations

import argparse
import html
import re
from collections import Counter
from pathlib import Path
from typing import Any

from benchmark_common import (
    AEB_ROOT,
    AUDIT_PATH,
    EVIDENCE_PATH,
    GRAPH_PATH,
    QUESTIONS_PATH,
    sha256_file,
    write_jsonl,
)


SOURCES = {
    "gb39901": {
        "file": "corpus/prepared/GB+39901-2025.pdf_by_PaddleOCR-VL-1.6.md",
        "title": "GB 39901—2025 轻型汽车自动紧急制动系统技术要求及试验方法",
    },
    "unece_r152": {
        "file": "corpus/prepared/unece_r152_rev2.md",
        "title": "UN Regulation No. 152 Revision 2",
    },
    "euroncap_c2c": {
        "file": "corpus/prepared/euroncap_aeb_c2c_v431.md",
        "title": "Euro NCAP AEB Car-to-Car Test Protocol v4.3.1",
    },
    "euroncap_score": {
        "file": "corpus/prepared/euroncap_collision_avoidance_v1041.md",
        "title": "Euro NCAP Collision Avoidance Assessment Protocol v10.4.1",
    },
}


def source_path(source_id: str) -> Path:
    return AEB_ROOT / SOURCES[source_id]["file"]


def extract(source_id: str, start: str, end: str | None = None) -> str:
    text = source_path(source_id).read_text(encoding="utf-8")
    start_at = text.find(start)
    if start_at < 0:
        raise RuntimeError(f"Missing start marker in {source_id}: {start}")
    if end is None:
        return start
    end_at = text.find(end, start_at + len(start))
    if end_at < 0:
        raise RuntimeError(f"Missing end marker in {source_id}: {end}")
    return text[start_at:end_at].strip()


def extract_table_row(excerpt: str, facts: dict[str, Any]) -> str:
    """Return the exact source HTML row selected by a table evidence record."""
    target_speed = facts.get("target_kmh", facts.get("target_start_kmh"))
    expected = [facts.get("ego_kmh"), target_speed, facts.get("kerb_kmh"), facts.get("gross_kmh")]
    expected_cells = [str(value) for value in expected]
    for row in re.findall(r"<tr>[\s\S]*?</tr>", excerpt):
        cells = [
            html.unescape(re.sub(r"<[^>]+>", "", cell)).strip()
            for cell in re.findall(r"<td[^>]*>([\s\S]*?)</td>", row)
        ]
        if cells == expected_cells:
            return row
    raise RuntimeError(f"Unable to locate table row {expected_cells} in excerpt")


EVIDENCE_SPECS: list[dict[str, Any]] = [
    {
        "id": "gb39901:clause:1",
        "source": "gb39901",
        "locator": {"clause": "1"},
        "title": "范围",
        "start": "本文件规定了  $ M_{1} $ 和  $ N_{1} $ 类汽车自动紧急制动系统的一般要求、性能要求与同一型式判定，描述了相应的试验方法。",
        "end": "## 2 规范性引用文件",
        "facts": {"vehicle_categories": ["M1", "N1"]},
    },
    {
        "id": "gb39901:clause:3.1",
        "source": "gb39901",
        "locator": {"clause": "3.1"},
        "title": "自动紧急制动系统定义",
        "start": "实时监测车辆前方行驶环境，并在可能发生碰撞危险时发出警告信号并自动启动车辆行车制动系统使车辆减速，以避免碰撞或减轻碰撞后果的系统。",
        "facts": {"term": "AEBS"},
    },
    {
        "id": "gb39901:clause:3.8",
        "source": "gb39901",
        "locator": {"clause": "3.8"},
        "title": "相对碰撞速度定义",
        "start": "在车辆运动方向上，发生碰撞时车辆与碰撞目标速度的差值。",
        "facts": {"term": "relative collision velocity"},
    },
    {
        "id": "gb39901:clause:4.2",
        "source": "gb39901",
        "locator": {"clause": "4.2"},
        "title": "自检",
        "start": "系统应至少具备以下自检功能：",
        "end": "### 4.3 系统状态",
        "facts": {"checks": ["电气部件", "传感元件"]},
    },
    {
        "id": "gb39901:clause:4.3.1.1",
        "source": "gb39901",
        "locator": {"clause": "4.3.1.1"},
        "title": "系统主动关闭限制",
        "start": "4.3.1.1 系统应在车辆每次进入新的上电/点火周期时自动开启",
        "end": "4.3.1.2 若系统可自动关闭",
        "facts": {"manual_deactivation_forbidden_above_kmh": 10},
    },
    {
        "id": "gb39901:clause:4.3.2.1",
        "source": "gb39901",
        "locator": {"clause": "4.3.2.1"},
        "title": "初始化未完成警告",
        "start": "4.3.2.1 当车辆速度大于  $ 10 \, km/h $，且累计行驶  $ 15 \, s $ 后",
        "end": "4.3.2.2 在发生可探测的",
        "facts": {"speed_operator": ">", "speed_kmh": 10, "elapsed_s": 15},
    },
    {
        "id": "gb39901:clause:4.3.2.2",
        "source": "gb39901",
        "locator": {"clause": "4.3.2.2"},
        "title": "故障警告时机",
        "start": "4.3.2.2 在发生可探测的、导致系统处于不可用状态或无法符合本文件要求的电子电气故障时",
        "end": "4.3.2.3 当车辆每次进入新的上电/点火周期时",
        "facts": {"electrical_fault_warning": "不应延迟", "numeric_seconds": None},
    },
    {
        "id": "gb39901:clause:4.3.2.4",
        "source": "gb39901",
        "locator": {"clause": "4.3.2.4"},
        "title": "故障警告信号",
        "start": "4.3.2.4 系统的故障警告信号应至少包括光学警告信号",
        "end": "4.3.2.5 当系统探测到与前方目标存在碰撞危险时",
        "facts": {"optical_signal": "常亮黄色"},
    },
    {
        "id": "gb39901:implementation:date",
        "source": "gb39901",
        "locator": {"clause": "9"},
        "title": "实施日期",
        "start": "2028-01-01 实施",
        "facts": {"effective_date": "2028-01-01"},
    },
    {
        "id": "gb39901:table:1:row:60",
        "source": "gb39901",
        "locator": {"clause": "5.2.1.1", "table": "1", "row": "vehicle_speed=60"},
        "title": "M1 静止车辆目标相对碰撞速度阈值",
        "start": "表1  $ M_{1} $ 类汽车最大相对碰撞速度要求——静止车辆目标场景",
        "end": "表2  $ N_{1} $ 类汽车最大相对碰撞速度要求——静止车辆目标场景",
        "facts": {"vehicle": "M1", "scenario": "stationary", "ego_kmh": 60, "target_kmh": 0, "kerb_kmh": 35, "gross_kmh": 35},
    },
    {
        "id": "gb39901:table:2:row:40",
        "source": "gb39901",
        "locator": {"clause": "5.2.1.2", "table": "2", "row": "vehicle_speed=40"},
        "title": "N1 静止车辆目标相对碰撞速度阈值",
        "start": "表2  $ N_{1} $ 类汽车最大相对碰撞速度要求——静止车辆目标场景",
        "end": "表 3  $ M_{1} $ 类汽车最大相对碰撞速度要求——匀速车辆目标场景",
        "facts": {"vehicle": "N1", "scenario": "stationary", "ego_kmh": 40, "target_kmh": 0, "kerb_kmh": 0, "gross_kmh": 10},
    },
    {
        "id": "gb39901:table:2:row:60",
        "source": "gb39901", "locator": {"clause": "5.2.1.2", "table": "2", "row": "vehicle_speed=60"},
        "title": "N1 静止车辆目标相对碰撞速度阈值",
        "start": "表2  $ N_{1} $ 类汽车最大相对碰撞速度要求——静止车辆目标场景",
        "end": "表 3  $ M_{1} $ 类汽车最大相对碰撞速度要求——匀速车辆目标场景",
        "facts": {"vehicle": "N1", "scenario": "stationary", "ego_kmh": 60, "target_kmh": 0, "kerb_kmh": 35, "gross_kmh": 40},
    },
    {
        "id": "gb39901:table:2",
        "source": "gb39901", "locator": {"clause": "5.2.1.2", "table": "2"},
        "title": "N1 静止车辆目标相对碰撞速度完整取值范围",
        "start": "表2  $ N_{1} $ 类汽车最大相对碰撞速度要求——静止车辆目标场景",
        "end": "表 3  $ M_{1} $ 类汽车最大相对碰撞速度要求——匀速车辆目标场景",
        "facts": {"vehicle": "N1", "scenario": "stationary", "available_ego_kmh": [10, 20, 40, 60]},
    },
    {
        "id": "gb39901:table:3:row:80",
        "source": "gb39901", "locator": {"clause": "5.2.1.1", "table": "3", "row": "vehicle_speed=80,target_speed=20"},
        "title": "M1 匀速车辆目标相对碰撞速度阈值",
        "start": "表 3  $ M_{1} $ 类汽车最大相对碰撞速度要求——匀速车辆目标场景",
        "end": "表4  $ N_{1} $ 类汽车最大相对碰撞速度要求——匀速车辆目标场景",
        "facts": {"vehicle": "M1", "scenario": "moving", "ego_kmh": 80, "target_kmh": 20, "kerb_kmh": 35, "gross_kmh": 35},
    },
    {
        "id": "gb39901:table:4:row:60",
        "source": "gb39901", "locator": {"clause": "5.2.1.2", "table": "4", "row": "vehicle_speed=60,target_speed=20"},
        "title": "N1 匀速车辆目标相对碰撞速度阈值",
        "start": "表4  $ N_{1} $ 类汽车最大相对碰撞速度要求——匀速车辆目标场景",
        "end": "表 5  $ M_{1} $ 类汽车最大相对碰撞速度要求——制动车辆目标场景",
        "facts": {"vehicle": "N1", "scenario": "moving", "ego_kmh": 60, "target_kmh": 20, "kerb_kmh": 0, "gross_kmh": 10},
    },
    {
        "id": "gb39901:table:6:row:50",
        "source": "gb39901", "locator": {"clause": "5.2.1.2", "table": "6", "row": "vehicle_speed=50,target_start_speed=50"},
        "title": "N1 制动车辆目标相对碰撞速度阈值",
        "start": "表 6  $ N_{1} $ 类汽车最大相对碰撞速度要求——制动车辆目标场景",
        "end": "#### 5.2.2 对于儿童行人目标的紧急制动能力",
        "facts": {"vehicle": "N1", "scenario": "braking", "ego_kmh": 50, "target_start_kmh": 50, "kerb_kmh": 0, "gross_kmh": 10},
    },
    {
        "id": "gb39901:table:7:row:60",
        "source": "gb39901", "locator": {"clause": "5.2.2", "table": "7", "row": "vehicle_speed=60,target_speed=5"},
        "title": "M1 儿童行人横穿相对碰撞速度阈值",
        "start": "表 7  $ M_{1} $ 类汽车最大相对碰撞速度要求——儿童行人目标横穿场景",
        "end": "表 8  $ N_{1} $ 类汽车最大相对碰撞速度要求——儿童行人目标横穿场景",
        "facts": {"vehicle": "M1", "target": "child", "ego_kmh": 60, "target_kmh": 5, "kerb_kmh": 35, "gross_kmh": 35},
    },
    {
        "id": "gb39901:table:8:row:40",
        "source": "gb39901", "locator": {"clause": "5.2.2", "table": "8", "row": "vehicle_speed=40,target_speed=5"},
        "title": "N1 儿童行人横穿相对碰撞速度阈值",
        "start": "表 8  $ N_{1} $ 类汽车最大相对碰撞速度要求——儿童行人目标横穿场景",
        "end": "#### 5.2.3 对于自行车目标的紧急制动能力",
        "facts": {"vehicle": "N1", "target": "child", "ego_kmh": 40, "target_kmh": 5, "kerb_kmh": 0, "gross_kmh": 10},
    },
    {
        "id": "gb39901:table:10:row:60",
        "source": "gb39901", "locator": {"clause": "5.2.3", "table": "10", "row": "vehicle_speed=60,target_speed=15"},
        "title": "N1 自行车横穿相对碰撞速度阈值",
        "start": "表 10  $ N_{1} $ 类汽车最大相对碰撞速度要求——自行车目标横穿场景",
        "end": "#### 5.2.4 对于踏板式两轮摩托车目标的紧急制动能力",
        "facts": {"vehicle": "N1", "target": "bicycle", "ego_kmh": 60, "target_kmh": 15, "kerb_kmh": 40, "gross_kmh": 45},
    },
    {
        "id": "gb39901:table:12:row:40",
        "source": "gb39901", "locator": {"clause": "5.2.4", "table": "12", "row": "vehicle_speed=40,target_speed=20"},
        "title": "N1 踏板式两轮摩托车横穿相对碰撞速度阈值",
        "start": "表 12  $ N_{1} $ 类汽车最大相对碰撞速度要求——踏板式两轮摩托车目标横穿场景",
        "end": "### 5.3 系统鲁棒性",
        "facts": {"vehicle": "N1", "target": "PTW", "ego_kmh": 40, "target_kmh": 20, "kerb_kmh": 0, "gross_kmh": 25},
    },
    {
        "id": "gb39901:clause:5.1.1",
        "source": "gb39901", "locator": {"clause": "5.1.1"}, "title": "车辆目标碰撞预警能力",
        "start": "#### 5.1.1 对于车辆目标的碰撞预警能力", "end": "#### 5.1.2 对于儿童行人目标的碰撞预警能力",
        "facts": {"tests": ["6.5", "6.6", "6.7"], "warning_lead_s": 0.8, "exception": "未发生碰撞时不迟于紧急制动"},
    },
    {
        "id": "gb39901:clause:5.2.1.2",
        "source": "gb39901", "locator": {"clause": "5.2.1.2"}, "title": "N1 车辆目标紧急制动能力",
        "start": "5.2.1.2 对于  $ N_{1} $ 类汽车，系统应符合以下要求：", "end": "<div style=\"text-align: center;\"><div style=\"text-align: center;\">表1",
        "facts": {"speed_range_kmh": [20, 60], "relative_speed_operator": ">", "relative_speed_kmh": 10, "min_deceleration_mps2": 5.0},
    },
    {
        "id": "gb39901:clause:5.2.2",
        "source": "gb39901", "locator": {"clause": "5.2.2"}, "title": "儿童行人目标紧急制动能力",
        "start": "#### 5.2.2 对于儿童行人目标的紧急制动能力", "end": "表 7  $ M_{1} $ 类汽车最大相对碰撞速度要求",
        "facts": {"test": "6.8", "min_deceleration_mps2": 5.0},
    },
    {
        "id": "gb39901:clause:5.2.3",
        "source": "gb39901", "locator": {"clause": "5.2.3"}, "title": "自行车目标紧急制动能力",
        "start": "#### 5.2.3 对于自行车目标的紧急制动能力", "end": "表 9  $ M_{1} $ 类汽车最大相对碰撞速度要求",
        "facts": {"test": "6.9", "min_deceleration_mps2": 5.0},
    },
    {
        "id": "gb39901:clause:5.2.4",
        "source": "gb39901", "locator": {"clause": "5.2.4"}, "title": "踏板式两轮摩托车目标紧急制动能力",
        "start": "#### 5.2.4 对于踏板式两轮摩托车目标的紧急制动能力", "end": "表 11  $ M_{1} $ 类汽车最大相对碰撞速度要求",
        "facts": {"test": "6.10", "min_deceleration_mps2": 5.0},
    },
    {
        "id": "gb39901:clause:5.4",
        "source": "gb39901", "locator": {"clause": "5.4"}, "title": "系统误响应要求",
        "start": "### 5.4 系统误响应", "end": "### 5.5 关闭碰撞预警后的系统紧急制动能力",
        "facts": {"test": "6.11", "forbidden": ["碰撞预警", "紧急制动"]},
    },
    {
        "id": "gb39901:clause:5.5",
        "source": "gb39901", "locator": {"clause": "5.5"}, "title": "关闭碰撞预警后的紧急制动能力",
        "start": "### 5.5 关闭碰撞预警后的系统紧急制动能力", "end": "### 5.6 关闭紧急制动后的系统碰撞预警能力",
        "facts": {"test": "6.12", "min_deceleration_mps2": 5.0, "tables": [1, 2]},
    },
    {
        "id": "gb39901:clause:5.6",
        "source": "gb39901", "locator": {"clause": "5.6"}, "title": "关闭紧急制动后的碰撞预警能力",
        "start": "### 5.6 关闭紧急制动后的系统碰撞预警能力", "end": "## 6 试验方法",
        "facts": {"test": "6.13", "ttc_lower_factor": 0.9, "ttc_upper_factor": 1.1},
    },
    {
        "id": "gb39901:clause:6.5-6.7",
        "source": "gb39901", "locator": {"clauses": ["6.5", "6.6", "6.7"]}, "title": "三类车辆目标试验",
        "start": "### 6.5 静止车辆目标的碰撞预警和紧急制动试验", "end": "### 6.8 儿童行人目标横穿的碰撞预警和紧急制动试验",
        "facts": {"scenarios": ["静止车辆目标", "匀速车辆目标", "制动车辆目标"]},
    },
    {
        "id": "gb39901:clause:6.8",
        "source": "gb39901", "locator": {"clause": "6.8"}, "title": "儿童行人横穿试验",
        "start": "### 6.8 儿童行人目标横穿的碰撞预警和紧急制动试验", "end": "### 6.9 自行车目标横穿的碰撞预警和紧急制动试验",
        "facts": {"target_speed_kmh": 5, "start_ttc_operator": ">=", "start_ttc_s": 4},
    },
    {
        "id": "gb39901:clause:6.9",
        "source": "gb39901", "locator": {"clause": "6.9"}, "title": "自行车横穿试验",
        "start": "### 6.9 自行车目标横穿的碰撞预警和紧急制动试验", "end": "### 6.10 踏板式两轮摩托车目标横穿的碰撞预警和紧急制动试验",
        "facts": {"target_speed_kmh": 15, "tolerance": "+0/-1", "start_ttc_operator": ">=", "start_ttc_s": 4},
    },
    {
        "id": "gb39901:clause:6.10",
        "source": "gb39901", "locator": {"clause": "6.10"}, "title": "踏板式两轮摩托车横穿试验",
        "start": "### 6.10 踏板式两轮摩托车目标横穿的碰撞预警和紧急制动试验", "end": "### 6.11 误响应试验",
        "facts": {"target_speed_kmh": 20, "tolerance": "+0/-1", "start_ttc_operator": ">=", "start_ttc_s": 4},
    },
    {
        "id": "gb39901:clause:6.11",
        "source": "gb39901", "locator": {"clause": "6.11"}, "title": "五类误响应试验",
        "start": "### 6.11 误响应试验", "end": "### 6.12 关闭碰撞预警后的系统紧急制动试验",
        "facts": {"scenario_count": 5},
    },
    {
        "id": "gb39901:clause:6.12",
        "source": "gb39901", "locator": {"clause": "6.12"}, "title": "关闭碰撞预警后的紧急制动试验",
        "start": "### 6.12 关闭碰撞预警后的系统紧急制动试验", "end": "### 6.13 关闭紧急制动后的系统碰撞预警试验",
        "facts": {"ego_kmh": 60, "start_ttc_operator": ">=", "start_ttc_s": 4},
    },
    {
        "id": "gb39901:clause:6.13",
        "source": "gb39901", "locator": {"clause": "6.13"}, "title": "关闭紧急制动后的碰撞预警试验",
        "start": "### 6.13 关闭紧急制动后的系统碰撞预警试验", "end": "### 6.14 仿真试验",
        "facts": {"ego_kmh": 60, "start_ttc_operator": ">=", "start_ttc_s": 4},
    },
    {
        "id": "gb39901:clause:6.14",
        "source": "gb39901", "locator": {"clause": "6.14"}, "title": "仿真试验替代与场地复核",
        "start": "### 6.14 仿真试验", "end": "## 7 说明书",
        "facts": {"substitutable_tests": "6.5-6.10", "minimum_field_tests": 1, "disagreement_third_test": "场地试验"},
    },
    {
        "id": "gb39901:appendix:B.2",
        "source": "gb39901", "locator": {"appendix": "B", "clause": "B.2"}, "title": "仿真工具链可信度评估",
        "start": "### B.2 仿真试验可信度评估", "end": "### B.3 使用仿真工具链进行试验的要求",
        "facts": {"dimensions": ["能力", "准确性", "正确性", "适用性", "可用性"]},
    },
    {
        "id": "gb39901:appendix:A.2.3",
        "source": "gb39901", "locator": {"appendix": "A", "clause": "A.2.3", "table": "A.1"}, "title": "危害分析、ASIL 与安全目标",
        "start": "### A.2.3 危害分析和风险评估", "end": "### A.2.4 安全措施说明",
        "facts": {"unexpected_lateral_motion_asil": "D"},
    },
    {
        "id": "gb39901:appendix:A.3.3",
        "source": "gb39901", "locator": {"appendix": "A", "clause": "A.3.3", "table": "A.2"}, "title": "功能安全故障注入验证",
        "start": "### A.3.3 功能安全概念的验证和确认", "end": "### A.3.4 验证和确认的结论",
        "facts": {"method": "故障注入", "purpose": "验证安全措施覆盖并实现安全目标"},
    },
    {
        "id": "gb39901:clause:3.12",
        "source": "gb39901", "locator": {"clause": "3.12"}, "title": "电子控制系统定义与示例组件",
        "start": "### 3.12", "end": "3.13",
        "facts": {"typical_components": ["传感器", "控制器", "执行器"], "status": "通常包括而非强制指定硬件"},
    },
    {
        "id": "gb39901:clause:4.1",
        "source": "gb39901", "locator": {"clause": "4.1"}, "title": "车型与目标激活速度范围",
        "start": "### 4.1 通用要求", "end": "### 4.2 自检",
        "facts": {"M1_vehicle_kmh": [10, 80], "N1_vehicle_kmh": [10, 60], "VRU_kmh": [20, 60]},
    },
    {
        "id": "gb39901:clause:5.3",
        "source": "gb39901", "locator": {"clause": "5.3"}, "title": "系统鲁棒性通过率",
        "start": "### 5.3 系统鲁棒性", "end": "### 5.4 系统误响应",
        "facts": {"vehicle_percent": 90, "child_percent": 90, "bicycle_percent": 80, "PTW_percent": 80},
    },
    {
        "id": "gb39901:clause:6.1.1",
        "source": "gb39901", "locator": {"clause": "6.1.1"}, "title": "不同试验的车辆载荷",
        "start": "#### 6.1.1 试验车辆载荷", "end": "#### 6.1.2 试验预处理",
        "facts": {"tests_6.5_6.10": ["行车质量", "最大设计总质量"], "tests_6.11_6.13": ["最大设计总质量"]},
    },
    {
        "id": "gb39901:clause:6.1.2.2",
        "source": "gb39901", "locator": {"clause": "6.1.2.2"}, "title": "可调激活时机选择",
        "start": "6.1.2.2 若系统的激活时机可由驾驶员主动调节",
        "facts": {"latest": ["6.5-6.10", "6.12-6.13"], "earliest": ["6.11"]},
    },
    {
        "id": "gb39901:clause:6.3",
        "source": "gb39901", "locator": {"clause": "6.3"}, "title": "试验目标要求",
        "start": "### 6.3 试验目标", "end": "### 6.4 试验条件",
        "facts": {"vehicle_target": ["ISO 19206-3", "大批量生产的普通乘用车"]},
    },
    {
        "id": "gb39901:clause:6.4",
        "source": "gb39901", "locator": {"clause": "6.4"}, "title": "试验环境与光照条件",
        "start": "### 6.4 试验条件", "end": "### 6.5 静止车辆目标的碰撞预警和紧急制动试验",
        "facts": {"tests_6.5_6.7_min_lux": 1000, "other_tests_min_lux": 2000},
    },
    {
        "id": "gb39901:clause:7",
        "source": "gb39901", "locator": {"clause": "7"}, "title": "产品使用说明书内容",
        "start": "## 7 说明书", "end": "## 8 同一型式判定",
        "facts": {"required_content_count": 4},
    },
    {
        "id": "gb39901:clause:8",
        "source": "gb39901", "locator": {"clause": "8", "subclauses": ["8.1", "8.2"]}, "title": "一般与功能安全同一型式条件",
        "start": "## 8 同一型式判定", "end": "## 9 标准的实施",
        "facts": {"general": "8.1", "functional_safety": "8.2"},
    },
    {
        "id": "gb39901:clause:9",
        "source": "gb39901", "locator": {"clause": "9"}, "title": "分阶段实施规则",
        "start": "## 9 标准的实施", "end": "#### 附录A",
        "facts": {"new_M1_general_month": 0, "approved_M1_general_month": 13, "new_N1_general_month": 13, "approved_N1_month": 25, "PTW_month": 25},
    },
    {
        "id": "gb39901:appendix:A.2.1",
        "source": "gb39901", "locator": {"appendix": "A", "clause": "A.2.1"}, "title": "提交与备查文档",
        "start": "### A.2.1 总体要求", "end": "### A.2.2 系统描述",
        "facts": {"submitted_count": 8, "retained_count": 6},
    },
    {
        "id": "gb39901:appendix:A.2-A.3",
        "source": "gb39901", "locator": {"appendix": "A", "clauses": ["A.2.3", "A.2.4", "A.2.5", "A.2.6", "A.3"]}, "title": "功能安全闭环",
        "start": "### A.2.3 危害分析和风险评估", "end": "#### 附录 B",
        "facts": {"stages": ["危害分析与风险评估", "安全措施", "安全分析", "验证确认计划", "故障注入验证", "结论"]},
    },
    {
        "id": "gb39901:appendix:C.2",
        "source": "gb39901", "locator": {"appendix": "C", "clause": "C.2"}, "title": "系统功能安全描述内容",
        "start": "### C.2 内容要求", "end": "GB 39901—2025",
        "facts": {"sections": ["系统描述", "危害分析和风险评估总结", "安全措施说明", "其他要求"]},
    },
    {
        "id": "unece_r152:clause:1",
        "source": "unece_r152", "locator": {"page": 5, "clause": "1"}, "title": "UNECE R152适用范围",
        "start": "### 1. Scope", "end": "### 2. Definitions",
        "facts": {"vehicle_categories": ["M1", "N1"], "targets": ["passenger car", "pedestrian", "bicycle"]},
    },
    {
        "id": "unece_r152:clause:2.1",
        "source": "unece_r152", "locator": {"page": 5, "clause": "2.1"}, "title": "UNECE AEBS定义",
        "start": "2.1. \"Advanced Emergency Braking System (AEBS)\" means", "end": "2.2. \"Emergency Braking\"",
        "facts": {"actions": ["detect imminent forward collision", "activate braking", "avoid or mitigate"]},
    },
    {
        "id": "unece_r152:clause:5.1.4.1.2",
        "source": "unece_r152", "locator": {"page": 7, "clause": "5.1.4.1.2"}, "title": "UNECE初始化状态提示",
        "start": "### 5.1.4.1.2. If the system has not been initialised", "end": "5.1.4.1.3. Upon detection",
        "facts": {"speed_kmh": 10, "elapsed_s": 15},
    },
    {
        "id": "unece_r152:clause:5.2.1.1",
        "source": "unece_r152", "locator": {"page": 8, "clause": "5.2.1.1"}, "title": "UNECE车辆目标碰撞预警时机",
        "start": "### 5.2.1.1. Collision warning", "end": "### 5.2.1.2. Emergency braking",
        "facts": {"normal_lead_s": 0.8, "exception": "cannot be anticipated in time", "latest": "start of emergency braking"},
    },
    {
        "id": "unece_r152:clause:6.1.5",
        "source": "unece_r152", "locator": {"page": 15, "clause": "6.1.5"}, "title": "UNECE试验光照",
        "start": "### 6.1.5. Natural ambient illumination", "end": "### 6.1.6. At the request",
        "facts": {"car_lux": 1000, "pedestrian_lux": 2000, "bicycle_lux": 2000},
    },
    {
        "id": "unece_r152:clause:6.3.1",
        "source": "unece_r152", "locator": {"page": 16, "clause": "6.3.1"}, "title": "UNECE车辆目标",
        "start": "### 6.3.1. The target used for the vehicle detection tests", "end": "6.3.2. The target used for the pedestrian",
        "facts": {"alternatives": ["production M1 passenger car", "soft target ISO 19206-3:2020"]},
    },
    {
        "id": "unece_r152:annex3:appendix2",
        "source": "unece_r152", "locator": {"annex": "3", "appendix": "2"}, "title": "UNECE误响应场景证据",
        "start": "False Reaction scenarios\n\nThe following scenarios shall be used", "end": "(a) Definition of overlap ratio",
        "facts": {"evidence_types": ["simulation results", "real-world test data", "track test data"]},
    },
    {
        "id": "euroncap_c2c:clause:2.2",
        "source": "euroncap_c2c", "locator": {"page": 7, "clause": "2.2"}, "title": "Euro NCAP车辆场景定义",
        "start": "### 2.2 Test Scenarios", "end": "Car-to-Car Front Turn-Across-Path",
        "facts": {"CCRs": "stationary", "CCRm": "constant speed", "CCRb": "then decelerates"},
    },
    {
        "id": "euroncap_c2c:clause:5.1",
        "source": "euroncap_c2c", "locator": {"page": 12, "clause": "5.1"}, "title": "Euro NCAP GVT与ISO要求",
        "start": "### 5 GLOBAL VEHICLE TARGET", "end": "## Source page 14",
        "facts": {"target": "GVT", "standard": "ISO 19206-3:2021"},
    },
    {
        "id": "euroncap_c2c:clause:7.2.3",
        "source": "euroncap_c2c", "locator": {"page": 16, "clause": "7.2.3"}, "title": "Euro NCAP日光试验光照",
        "start": "### 7.2.3 Natural ambient illumination", "end": "### 7.2.4 Measure and record",
        "facts": {"daylight_lux_operator": ">", "daylight_lux": 2000},
    },
    {
        "id": "euroncap_score:clause:3.3",
        "source": "euroncap_score", "locator": {"page": 8, "clause": "3.3"}, "title": "Euro NCAP评分资格与指标",
        "start": "### 3.3 Criteria and Scoring", "end": "### 3.3.2 Car-to-Car Rear",
        "facts": {"CCRs_CCRb_metric": "Vimpact", "CCRm_metric": "Vrel_impact", "CCFtap_metric": "collision avoidance"},
    },
]


def evidence_records() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for spec in EVIDENCE_SPECS:
        source_id = spec["source"]
        excerpt = extract(source_id, spec["start"], spec.get("end"))
        if spec.get("locator", {}).get("table") and spec.get("locator", {}).get("row"):
            excerpt = extract_table_row(excerpt, spec.get("facts", {}))
        records.append(
            {
                "id": spec["id"],
                "source_id": source_id,
                "source_file": SOURCES[source_id]["file"],
                "source_title": SOURCES[source_id]["title"],
                "source_sha256": sha256_file(source_path(source_id)),
                "locator": spec["locator"],
                "title": spec["title"],
                "source_excerpt": excerpt,
                "normalized_facts": spec.get("facts", {}),
            }
        )
    return records


def claim(text: str, *evidence_ids: str) -> dict[str, Any]:
    return {"text": text, "evidence_ids": list(evidence_ids)}


QUESTION_SPECS: list[dict[str, Any]] = [
    {
        "id": "gb_direct_001",
        "question": "GB 39901—2025 适用于哪两类汽车？",
        "task_type": "direct_fact",
        "answer": {"vehicle_categories": ["M1", "N1"]},
        "claims": [claim("本文件适用于 M1 类汽车。", "gb39901:clause:1"), claim("本文件适用于 N1 类汽车。", "gb39901:clause:1")],
        "evidence": ["gb39901:clause:1"],
        "steps": [("Standard", "GB 39901—2025"), ("Clause", "第1章 范围"), ("VehicleCategorySet", "M1类和N1类汽车")],
        "reason": "直接事实控制题；完整答案位于同一范围条款，不预期图检索优于高质量向量检索。",
    },
    {
        "id": "gb_direct_002",
        "question": "GB 39901—2025 如何定义自动紧急制动系统（AEBS）？",
        "task_type": "direct_fact",
        "answer": {"definition": "实时监测车辆前方行驶环境，在可能发生碰撞危险时发出警告信号并自动启动车辆行车制动系统使车辆减速，以避免碰撞或减轻碰撞后果。"},
        "claims": [claim("AEBS 实时监测车辆前方行驶环境。", "gb39901:clause:3.1"), claim("可能发生碰撞危险时，AEBS 发出警告并自动启动车辆行车制动系统使车辆减速，以避免碰撞或减轻后果。", "gb39901:clause:3.1")],
        "evidence": ["gb39901:clause:3.1"],
        "steps": [("Standard", "GB 39901—2025"), ("Clause", "3.1"), ("Definition", "自动紧急制动系统定义")],
        "reason": "定义位于单一术语条款，是检索与回答的简单控制组。",
    },
    {
        "id": "gb_direct_003",
        "question": "标准中的“相对碰撞速度”指什么？",
        "task_type": "direct_fact",
        "answer": {"definition": "在车辆运动方向上，发生碰撞时车辆与碰撞目标速度的差值。"},
        "claims": [claim("相对碰撞速度是在车辆运动方向上发生碰撞时车辆与碰撞目标速度的差值。", "gb39901:clause:3.8")],
        "evidence": ["gb39901:clause:3.8"],
        "steps": [("Standard", "GB 39901—2025"), ("Clause", "3.8"), ("Definition", "相对碰撞速度定义")],
        "reason": "单条术语定义即可回答，用于衡量普通 RAG 的事实能力。",
    },
    {
        "id": "gb_direct_004",
        "question": "GB 39901—2025 从哪一天开始实施？",
        "task_type": "direct_fact",
        "answer": {"effective_date": "2028-01-01"},
        "claims": [claim("GB 39901—2025 自 2028 年 1 月 1 日开始实施。", "gb39901:implementation:date")],
        "evidence": ["gb39901:implementation:date"],
        "steps": [("Standard", "GB 39901—2025"), ("Clause", "第9章 实施过渡期"), ("Date", "2028年1月1日")],
        "reason": "日期精确匹配控制题，答案来自单一实施条款。",
    },
    {
        "id": "gb_direct_005",
        "question": "车辆速度大于多少时，驾驶员不能主动关闭 AEBS？",
        "task_type": "direct_fact",
        "answer": {"operator": ">", "speed": 10, "unit": "km/h"},
        "claims": [claim("车辆速度大于 10 km/h 时，系统无法被主动关闭。", "gb39901:clause:4.3.1.1")],
        "evidence": ["gb39901:clause:4.3.1.1"],
        "steps": [("Standard", "GB 39901—2025"), ("Clause", "4.3.1.1"), ("Threshold", "车辆速度>10 km/h")],
        "reason": "检验比较符、数值和单位是否同时保留，仍是单条款控制题。",
    },
    {
        "id": "gb_direct_006",
        "question": "系统在什么车速和累计行驶时间条件下仍未完成初始化时，必须发出光学警告？",
        "task_type": "direct_fact",
        "answer": {"speed_operator": ">", "speed": 10, "speed_unit": "km/h", "elapsed": 15, "elapsed_unit": "s", "action": "发出并持续光学警告直至完成初始化"},
        "claims": [claim("车辆速度大于 10 km/h 且累计行驶 15 s 后，系统若仍未完成初始化，应至少发出光学警告。", "gb39901:clause:4.3.2.1"), claim("警告应持续至系统完成初始化。", "gb39901:clause:4.3.2.1")],
        "evidence": ["gb39901:clause:4.3.2.1"],
        "steps": [("Standard", "GB 39901—2025"), ("Clause", "4.3.2.1"), ("Condition", "车速>10 km/h且累计行驶15 s"), ("Requirement", "发出并持续光学警告")],
        "reason": "虽在单条款内，但要求组合两个条件、动作和终止条件，用于检查条件完整性。",
    },
    {
        "id": "gb_direct_007",
        "question": "AEBS 的故障光学警告信号至少应采用什么颜色和显示方式？",
        "task_type": "direct_fact",
        "answer": {"color": "黄色", "display": "常亮"},
        "claims": [claim("故障光学警告信号应为常亮的黄色信号。", "gb39901:clause:4.3.2.4")],
        "evidence": ["gb39901:clause:4.3.2.4"],
        "steps": [("Standard", "GB 39901—2025"), ("Clause", "4.3.2.4"), ("Signal", "常亮黄色故障光学警告")],
        "reason": "单条款双属性事实控制题。",
    },
    {
        "id": "gb_direct_008",
        "question": "GB 39901—2025 要求 AEBS 至少自检哪两类对象？",
        "task_type": "direct_fact",
        "answer": {"items": ["相关电气部件是否正常运行", "相关传感元件是否正常运行"]},
        "claims": [claim("系统至少检查相关电气部件是否正常运行。", "gb39901:clause:4.2"), claim("系统至少检查相关传感元件是否正常运行。", "gb39901:clause:4.2")],
        "evidence": ["gb39901:clause:4.2"],
        "steps": [("Standard", "GB 39901—2025"), ("Clause", "4.2 自检"), ("RequirementSet", "电气部件和传感元件自检")],
        "reason": "小型完整枚举控制题，仍不依赖跨块图路径。",
        "scoring": "set_f1",
    },
    {
        "id": "gb_table_001",
        "question": "M1 类试验车辆以 60 km/h、静止车辆目标、最大设计总质量状态试验时，允许的最大相对碰撞速度是多少？",
        "task_type": "conditional_table",
        "answer": {"vehicle_category": "M1", "scenario": "静止车辆目标", "ego_speed": 60, "target_speed": 0, "load_state": "最大设计总质量", "max_relative_collision_speed": 35, "unit": "km/h"},
        "claims": [claim("适用车型为 M1 类。", "gb39901:table:1:row:60"), claim("场景为静止车辆目标，试验车速度为 60 km/h，目标速度为 0 km/h。", "gb39901:table:1:row:60"), claim("最大设计总质量状态下，最大相对碰撞速度为 35 km/h。", "gb39901:table:1:row:60")],
        "evidence": ["gb39901:table:1:row:60"],
        "steps": [("Requirement", "M1车辆目标紧急制动能力"), ("TestScenario", "静止车辆目标场景"), ("Condition", "试验车60 km/h且目标0 km/h"), ("LoadState", "最大设计总质量"), ("Threshold", "最大相对碰撞速度35 km/h")],
        "reason": "同一表格行包含答案，但必须沿车型—场景—速度—载荷—阈值条件选择正确单元格；用于表格结构恢复，不冒充跨章节多跳。",
    },
    {
        "id": "gb_table_002",
        "question": "N1 类试验车辆以 40 km/h 驶向静止车辆目标时，在最大设计总质量状态下允许的最大相对碰撞速度是多少？",
        "task_type": "conditional_table",
        "answer": {"vehicle_category": "N1", "scenario": "静止车辆目标", "ego_speed": 40, "target_speed": 0, "load_state": "最大设计总质量", "max_relative_collision_speed": 10, "unit": "km/h"},
        "claims": [claim("适用车型为 N1 类。", "gb39901:table:2:row:40"), claim("场景为静止车辆目标，试验车速度为 40 km/h，目标速度为 0 km/h。", "gb39901:table:2:row:40"), claim("最大设计总质量状态下，最大相对碰撞速度为 10 km/h。", "gb39901:table:2:row:40")],
        "evidence": ["gb39901:table:2:row:40"],
        "steps": [("Requirement", "N1车辆目标紧急制动能力"), ("TestScenario", "静止车辆目标场景"), ("Condition", "试验车40 km/h且目标0 km/h"), ("LoadState", "最大设计总质量"), ("Threshold", "最大相对碰撞速度10 km/h")],
        "reason": "必须区分 N1 与 M1、最大设计总质量与行车质量，并选择表2的40 km/h行。",
    },
    {
        "id": "gb_table_003", "task_type": "conditional_table",
        "question": "N1 类试验车辆以 60 km/h 驶向静止车辆目标时，在最大设计总质量状态下允许的最大相对碰撞速度是多少？",
        "answer": {"vehicle_category": "N1", "scenario": "静止车辆目标", "ego_speed": 60, "target_speed": 0, "load_state": "最大设计总质量", "max_relative_collision_speed": 40, "unit": "km/h"},
        "claims": [claim("适用车型为 N1 类。", "gb39901:table:2:row:60"), claim("试验车速度为60 km/h，静止目标速度为0 km/h。", "gb39901:table:2:row:60"), claim("最大设计总质量状态的最大相对碰撞速度为40 km/h。", "gb39901:table:2:row:60")],
        "evidence": ["gb39901:table:2:row:60"],
        "steps": [("Requirement", "N1车辆目标紧急制动能力"), ("TestScenario", "静止车辆目标场景"), ("Condition", "试验车60 km/h且目标0 km/h"), ("LoadState", "最大设计总质量"), ("Threshold", "最大相对碰撞速度40 km/h")],
        "reason": "与 M1 的相近表格行形成干扰，必须保留 N1、60 km/h 和总质量条件。",
    },
    {
        "id": "gb_table_004", "task_type": "conditional_table",
        "question": "M1 类试验车辆以 80 km/h 接近 20 km/h 匀速车辆目标时，在行车质量状态下允许的最大相对碰撞速度是多少？",
        "answer": {"vehicle_category": "M1", "scenario": "匀速车辆目标", "ego_speed": 80, "target_speed": 20, "load_state": "行车质量", "max_relative_collision_speed": 35, "unit": "km/h"},
        "claims": [claim("适用车型为 M1 类，场景为匀速车辆目标。", "gb39901:table:3:row:80"), claim("试验车速度为80 km/h，目标速度为20 km/h。", "gb39901:table:3:row:80"), claim("行车质量状态的最大相对碰撞速度为35 km/h。", "gb39901:table:3:row:80")],
        "evidence": ["gb39901:table:3:row:80"],
        "steps": [("Requirement", "M1车辆目标紧急制动能力"), ("TestScenario", "匀速车辆目标场景"), ("Condition", "试验车80 km/h且目标20 km/h"), ("LoadState", "行车质量"), ("Threshold", "最大相对碰撞速度35 km/h")],
        "reason": "检验模型能否区分试验车速度与目标速度，并选择行车质量列。",
    },
    {
        "id": "gb_table_005", "task_type": "conditional_table",
        "question": "N1 类试验车辆以 60 km/h 接近 20 km/h 匀速车辆目标时，在最大设计总质量状态下允许的最大相对碰撞速度是多少？",
        "answer": {"vehicle_category": "N1", "scenario": "匀速车辆目标", "ego_speed": 60, "target_speed": 20, "load_state": "最大设计总质量", "max_relative_collision_speed": 10, "unit": "km/h"},
        "claims": [claim("适用车型为 N1 类，场景为匀速车辆目标。", "gb39901:table:4:row:60"), claim("试验车速度为60 km/h，目标速度为20 km/h。", "gb39901:table:4:row:60"), claim("最大设计总质量状态的最大相对碰撞速度为10 km/h。", "gb39901:table:4:row:60")],
        "evidence": ["gb39901:table:4:row:60"],
        "steps": [("Requirement", "N1车辆目标紧急制动能力"), ("TestScenario", "匀速车辆目标场景"), ("Condition", "试验车60 km/h且目标20 km/h"), ("LoadState", "最大设计总质量"), ("Threshold", "最大相对碰撞速度10 km/h")],
        "reason": "需要联合车型、移动目标、两种速度和载荷条件定位表4单元格。",
    },
    {
        "id": "gb_table_006", "task_type": "conditional_table",
        "question": "N1 类制动车辆目标试验中，试验车和目标起始速度均为 50 km/h，最大设计总质量状态允许的最大相对碰撞速度是多少？",
        "answer": {"vehicle_category": "N1", "scenario": "制动车辆目标", "ego_speed": 50, "target_start_speed": 50, "load_state": "最大设计总质量", "max_relative_collision_speed": 10, "unit": "km/h"},
        "claims": [claim("适用车型为 N1 类，场景为制动车辆目标。", "gb39901:table:6:row:50"), claim("试验车与目标试验开始速度均为50 km/h。", "gb39901:table:6:row:50"), claim("最大设计总质量状态的最大相对碰撞速度为10 km/h。", "gb39901:table:6:row:50")],
        "evidence": ["gb39901:table:6:row:50"],
        "steps": [("Requirement", "N1车辆目标紧急制动能力"), ("TestScenario", "制动车辆目标场景"), ("Condition", "试验车50 km/h且目标起始50 km/h"), ("LoadState", "最大设计总质量"), ("Threshold", "最大相对碰撞速度10 km/h")],
        "reason": "检查目标起始速度与碰撞时相对速度的概念区分。",
    },
    {
        "id": "gb_table_007", "task_type": "conditional_table",
        "question": "M1 类试验车辆以 60 km/h 对 5 km/h 儿童行人横穿目标试验时，行车质量状态允许的最大相对碰撞速度是多少？",
        "answer": {"vehicle_category": "M1", "scenario": "儿童行人目标横穿", "ego_speed": 60, "target_speed": 5, "load_state": "行车质量", "max_relative_collision_speed": 35, "unit": "km/h"},
        "claims": [claim("适用车型为 M1 类，场景为儿童行人目标横穿。", "gb39901:table:7:row:60"), claim("试验车速度为60 km/h，儿童目标速度为5 km/h。", "gb39901:table:7:row:60"), claim("行车质量状态的最大相对碰撞速度为35 km/h。", "gb39901:table:7:row:60")],
        "evidence": ["gb39901:table:7:row:60"],
        "steps": [("Requirement", "儿童行人目标紧急制动能力"), ("TestScenario", "儿童行人目标横穿"), ("Condition", "试验车60 km/h且儿童目标5 km/h"), ("LoadState", "行车质量"), ("Threshold", "最大相对碰撞速度35 km/h")],
        "reason": "检验弱势道路使用者表格中的目标类型和载荷列选择。",
    },
    {
        "id": "gb_table_008", "task_type": "conditional_table",
        "question": "N1 类试验车辆以 40 km/h 对 5 km/h 儿童行人横穿目标试验时，最大设计总质量状态允许的最大相对碰撞速度是多少？",
        "answer": {"vehicle_category": "N1", "scenario": "儿童行人目标横穿", "ego_speed": 40, "target_speed": 5, "load_state": "最大设计总质量", "max_relative_collision_speed": 10, "unit": "km/h"},
        "claims": [claim("适用车型为 N1 类，场景为儿童行人目标横穿。", "gb39901:table:8:row:40"), claim("试验车速度为40 km/h，儿童目标速度为5 km/h。", "gb39901:table:8:row:40"), claim("最大设计总质量状态的最大相对碰撞速度为10 km/h。", "gb39901:table:8:row:40")],
        "evidence": ["gb39901:table:8:row:40"],
        "steps": [("Requirement", "儿童行人目标紧急制动能力"), ("TestScenario", "儿童行人目标横穿"), ("Condition", "试验车40 km/h且儿童目标5 km/h"), ("LoadState", "最大设计总质量"), ("Threshold", "最大相对碰撞速度10 km/h")],
        "reason": "与同表行车质量值0及60 km/h行总质量值40构成近似条件干扰。",
    },
    {
        "id": "gb_table_009", "task_type": "conditional_table",
        "question": "N1 类试验车辆以 60 km/h 对 15 km/h 自行车横穿目标试验时，最大设计总质量状态允许的最大相对碰撞速度是多少？",
        "answer": {"vehicle_category": "N1", "scenario": "自行车目标横穿", "ego_speed": 60, "target_speed": 15, "load_state": "最大设计总质量", "max_relative_collision_speed": 45, "unit": "km/h"},
        "claims": [claim("适用车型为 N1 类，场景为自行车目标横穿。", "gb39901:table:10:row:60"), claim("试验车速度为60 km/h，自行车目标速度为15 km/h。", "gb39901:table:10:row:60"), claim("最大设计总质量状态的最大相对碰撞速度为45 km/h。", "gb39901:table:10:row:60")],
        "evidence": ["gb39901:table:10:row:60"],
        "steps": [("Requirement", "自行车目标紧急制动能力"), ("TestScenario", "自行车目标横穿"), ("Condition", "试验车60 km/h且自行车目标15 km/h"), ("LoadState", "最大设计总质量"), ("Threshold", "最大相对碰撞速度45 km/h")],
        "reason": "目标速度15 km/h和阈值45 km/h容易混淆，要求保持字段角色。",
    },
    {
        "id": "gb_table_010", "task_type": "conditional_table",
        "question": "N1 类试验车辆以 40 km/h 对 20 km/h 踏板式两轮摩托车横穿目标试验时，最大设计总质量状态允许的最大相对碰撞速度是多少？",
        "answer": {"vehicle_category": "N1", "scenario": "踏板式两轮摩托车目标横穿", "ego_speed": 40, "target_speed": 20, "load_state": "最大设计总质量", "max_relative_collision_speed": 25, "unit": "km/h"},
        "claims": [claim("适用车型为 N1 类，场景为踏板式两轮摩托车目标横穿。", "gb39901:table:12:row:40"), claim("试验车速度为40 km/h，目标速度为20 km/h。", "gb39901:table:12:row:40"), claim("最大设计总质量状态的最大相对碰撞速度为25 km/h。", "gb39901:table:12:row:40")],
        "evidence": ["gb39901:table:12:row:40"],
        "steps": [("Requirement", "踏板式两轮摩托车目标紧急制动能力"), ("TestScenario", "踏板式两轮摩托车目标横穿"), ("Condition", "试验车40 km/h且目标20 km/h"), ("LoadState", "最大设计总质量"), ("Threshold", "最大相对碰撞速度25 km/h")],
        "reason": "必须区分目标速度20 km/h和允许相对碰撞速度25 km/h。",
    },
    {
        "id": "gb_multi_hop_001", "task_type": "multi_hop_relation",
        "question": "车辆目标碰撞预警能力应通过哪些试验验证，预警相对紧急制动的最迟时机是什么，并有什么例外？",
        "answer": {"tests": ["6.5 静止车辆目标", "6.6 匀速车辆目标", "6.7 制动车辆目标"], "normal_timing": "不迟于紧急制动前0.8 s", "exception": "若未发生碰撞，碰撞预警不迟于紧急制动发出"},
        "claims": [claim("车辆目标碰撞预警能力按6.5至6.7三类试验验证。", "gb39901:clause:5.1.1", "gb39901:clause:6.5-6.7"), claim("通常碰撞预警应不迟于紧急制动之前0.8 s发出。", "gb39901:clause:5.1.1"), claim("若未发生碰撞，碰撞预警应不迟于紧急制动发出。", "gb39901:clause:5.1.1")],
        "evidence": ["gb39901:clause:5.1.1", "gb39901:clause:6.5-6.7"],
        "steps": [("Requirement", "车辆目标碰撞预警能力", "gb39901:clause:5.1.1"), ("TestScenario", "6.5至6.7三类车辆目标试验", "gb39901:clause:6.5-6.7"), ("Condition", "发生碰撞或未发生碰撞", "gb39901:clause:5.1.1"), ("Threshold", "正常提前0.8 s，未碰撞时不迟于制动", "gb39901:clause:5.1.1")],
        "reason": "答案需要从性能要求追到三种试验场景，并保留未发生碰撞时的例外，单个试验块不含完整答案。",
        "scoring": "claim_f1",
    },
    {
        "id": "gb_multi_hop_002", "task_type": "multi_hop_relation",
        "question": "对 N1 类汽车的车辆目标紧急制动能力，哪些试验、速度与相对速度条件会触发至少 5.0 m/s² 的减速度要求？",
        "answer": {"vehicle_category": "N1", "tests": ["6.5", "6.6", "6.7"], "ego_speed_range": [20, 60], "ego_speed_unit": "km/h", "relative_speed_operator": ">", "relative_speed": 10, "relative_speed_unit": "km/h", "minimum_peak_deceleration": 5.0, "deceleration_unit": "m/s²"},
        "claims": [claim("该要求适用于N1类汽车并按6.5至6.7试验。", "gb39901:clause:5.2.1.2", "gb39901:clause:6.5-6.7"), claim("车辆速度范围为20 km/h至60 km/h。", "gb39901:clause:5.2.1.2"), claim("与车辆目标速度差大于10 km/h时，紧急制动最大减速度绝对值不小于5.0 m/s²。", "gb39901:clause:5.2.1.2")],
        "evidence": ["gb39901:clause:5.2.1.2", "gb39901:clause:6.5-6.7"],
        "steps": [("Requirement", "N1车辆目标紧急制动能力", "gb39901:clause:5.2.1.2"), ("TestScenario", "6.5至6.7三类车辆目标试验", "gb39901:clause:6.5-6.7"), ("Condition", "车速20至60 km/h且速度差>10 km/h", "gb39901:clause:5.2.1.2"), ("Threshold", "最大减速度绝对值>=5.0 m/s²", "gb39901:clause:5.2.1.2")],
        "reason": "需要关联N1性能条款与三个试验章节，同时精确保留两个速度条件、比较符和减速度阈值。",
    },
    {
        "id": "gb_multi_hop_003", "task_type": "multi_hop_relation",
        "question": "儿童行人目标紧急制动要求由哪个试验验证？该试验开始时的 TTC 和目标速度条件是什么？",
        "answer": {"test": "6.8 儿童行人目标横穿试验", "start_ttc_operator": ">=", "start_ttc": 4, "ttc_unit": "s", "target_speed": 5, "target_speed_tolerance": "±0.2", "speed_unit": "km/h", "minimum_peak_deceleration": 5.0, "deceleration_unit": "m/s²"},
        "claims": [claim("儿童行人目标紧急制动能力按6.8试验，最大减速度绝对值不小于5.0 m/s²。", "gb39901:clause:5.2.2"), claim("试验开始时TTC不小于4 s。", "gb39901:clause:6.8"), claim("儿童行人目标加速至(5±0.2) km/h横穿。", "gb39901:clause:6.8")],
        "evidence": ["gb39901:clause:5.2.2", "gb39901:clause:6.8"],
        "steps": [("Requirement", "儿童行人目标紧急制动能力", "gb39901:clause:5.2.2"), ("TestScenario", "6.8儿童行人目标横穿", "gb39901:clause:6.8"), ("Condition", "开始TTC>=4 s且目标5±0.2 km/h", "gb39901:clause:6.8"), ("Threshold", "最大减速度绝对值>=5.0 m/s²", "gb39901:clause:5.2.2")],
        "reason": "性能阈值在5.2.2，TTC和目标运动条件在6.8，必须跨条款组合。",
    },
    {
        "id": "gb_multi_hop_004", "task_type": "multi_hop_relation",
        "question": "自行车目标紧急制动要求由哪个试验验证？试验开始 TTC 和自行车目标速度（含偏差）是什么？",
        "answer": {"test": "6.9 自行车目标横穿试验", "start_ttc_operator": ">=", "start_ttc": 4, "ttc_unit": "s", "target_speed": 15, "target_speed_tolerance": "+0/-1", "speed_unit": "km/h", "minimum_peak_deceleration": 5.0, "deceleration_unit": "m/s²"},
        "claims": [claim("自行车目标紧急制动能力按6.9试验，最大减速度绝对值不小于5.0 m/s²。", "gb39901:clause:5.2.3"), claim("试验开始时TTC不小于4 s。", "gb39901:clause:6.9"), claim("自行车目标速度为15 km/h，偏差+0/-1 km/h。", "gb39901:clause:6.9")],
        "evidence": ["gb39901:clause:5.2.3", "gb39901:clause:6.9"],
        "steps": [("Requirement", "自行车目标紧急制动能力", "gb39901:clause:5.2.3"), ("TestScenario", "6.9自行车目标横穿", "gb39901:clause:6.9"), ("Condition", "开始TTC>=4 s且目标15 km/h(+0/-1)", "gb39901:clause:6.9"), ("Threshold", "最大减速度绝对值>=5.0 m/s²", "gb39901:clause:5.2.3")],
        "reason": "需跨性能和试验章节，并与儿童5 km/h、摩托车20 km/h相近条件区分。",
    },
    {
        "id": "gb_multi_hop_005", "task_type": "multi_hop_relation",
        "question": "踏板式两轮摩托车目标紧急制动要求由哪个试验验证？试验开始 TTC 和目标速度（含偏差）是什么？",
        "answer": {"test": "6.10 踏板式两轮摩托车目标横穿试验", "start_ttc_operator": ">=", "start_ttc": 4, "ttc_unit": "s", "target_speed": 20, "target_speed_tolerance": "+0/-1", "speed_unit": "km/h", "minimum_peak_deceleration": 5.0, "deceleration_unit": "m/s²"},
        "claims": [claim("踏板式两轮摩托车目标紧急制动能力按6.10试验，最大减速度绝对值不小于5.0 m/s²。", "gb39901:clause:5.2.4"), claim("试验开始时TTC不小于4 s。", "gb39901:clause:6.10"), claim("目标速度为20 km/h，偏差+0/-1 km/h。", "gb39901:clause:6.10")],
        "evidence": ["gb39901:clause:5.2.4", "gb39901:clause:6.10"],
        "steps": [("Requirement", "踏板式两轮摩托车目标紧急制动能力", "gb39901:clause:5.2.4"), ("TestScenario", "6.10踏板式两轮摩托车横穿", "gb39901:clause:6.10"), ("Condition", "开始TTC>=4 s且目标20 km/h(+0/-1)", "gb39901:clause:6.10"), ("Threshold", "最大减速度绝对值>=5.0 m/s²", "gb39901:clause:5.2.4")],
        "reason": "需把目标类型映射到6.10并跨块提取TTC、目标速度偏差和性能阈值。",
    },
    {
        "id": "gb_multi_hop_006", "task_type": "multi_hop_relation",
        "question": "系统无误响应要求与6.11试验是什么关系？6.11包含多少类子场景，共同通过行为是什么？",
        "answer": {"requirement_clause": "5.4", "test": "6.11", "scenario_count": 5, "pass_behavior": "不存在碰撞危险时不发出碰撞预警且不实施紧急制动"},
        "claims": [claim("5.4的无误响应要求通过6.11试验验证。", "gb39901:clause:5.4", "gb39901:clause:6.11"), claim("6.11包含五类子场景，共同要求无危险时不预警且不紧急制动。", "gb39901:clause:5.4", "gb39901:clause:6.11")],
        "evidence": ["gb39901:clause:5.4", "gb39901:clause:6.11"],
        "steps": [("Requirement", "系统无误响应", "gb39901:clause:5.4"), ("TestScenario", "6.11五类误响应试验", "gb39901:clause:6.11"), ("Condition", "不存在碰撞危险", "gb39901:clause:5.4"), ("AcceptanceCriterion", "不发预警且不紧急制动", "gb39901:clause:5.4")],
        "reason": "通过行为位于5.4、场景集合位于6.11，本题只测要求—试验—计数关系；完整枚举另由综合题测量。",
        "scoring": "claim_f1",
    },
    {
        "id": "gb_multi_hop_007", "task_type": "multi_hop_relation",
        "question": "若驾驶员部分关闭碰撞预警，如何试验剩余的紧急制动能力，性能通过条件是什么？",
        "answer": {"test": "6.12 静止车辆目标试验", "ego_speed": 60, "ego_speed_tolerance": "+0/-2", "speed_unit": "km/h", "start_ttc_operator": ">=", "start_ttc": 4, "ttc_unit": "s", "minimum_peak_deceleration": 5.0, "deceleration_unit": "m/s²", "collision_speed_requirement": "不大于表1或表2对应阈值"},
        "claims": [claim("关闭碰撞预警后按6.12试验，最大减速度绝对值不小于5.0 m/s²且相对碰撞速度不大于表1或表2阈值。", "gb39901:clause:5.5"), claim("6.12使用60 km/h（+0/-2）驶向静止车辆目标，开始TTC不小于4 s。", "gb39901:clause:6.12")],
        "evidence": ["gb39901:clause:5.5", "gb39901:clause:6.12"],
        "steps": [("Requirement", "关闭碰撞预警后紧急制动不降级", "gb39901:clause:5.5"), ("TestScenario", "6.12静止车辆目标试验", "gb39901:clause:6.12"), ("Condition", "60 km/h(+0/-2)且开始TTC>=4 s", "gb39901:clause:6.12"), ("Threshold", "减速度>=5.0 m/s²且碰撞速度符合表1/2", "gb39901:clause:5.5")],
        "reason": "性能条件在5.5，具体速度和TTC工况在6.12，且需映射车型到表1或表2。",
    },
    {
        "id": "gb_multi_hop_008", "task_type": "multi_hop_relation",
        "question": "若驾驶员部分关闭紧急制动，碰撞预警试验如何设置，预警 TTC 的允许区间如何由基准试验计算？",
        "answer": {"test": "6.13", "ego_speed": 60, "ego_speed_tolerance": "+0/-2", "speed_unit": "km/h", "start_ttc_operator": ">=", "start_ttc": 4, "ttc_unit": "s", "reference": "6.5中最大设计总质量、60 km/h试验", "lower_bound": "不小于基准较小TTC的0.9倍", "upper_bound": "不大于基准较大TTC的1.1倍"},
        "claims": [claim("关闭紧急制动后的预警TTC应为6.5最大设计总质量60 km/h基准较小值的至少0.9倍、较大值的至多1.1倍。", "gb39901:clause:5.6"), claim("6.13以60 km/h（+0/-2）驶向静止目标，开始TTC不小于4 s。", "gb39901:clause:6.13")],
        "evidence": ["gb39901:clause:5.6", "gb39901:clause:6.13", "gb39901:clause:6.5-6.7"],
        "steps": [("Requirement", "关闭紧急制动后碰撞预警不降级", "gb39901:clause:5.6"), ("TestScenario", "6.13静止车辆目标预警试验", "gb39901:clause:6.13"), ("ReferenceTest", "6.5最大设计总质量60 km/h基准", "gb39901:clause:6.5-6.7"), ("Threshold", "0.9×较小TTC至1.1×较大TTC", "gb39901:clause:5.6")],
        "reason": "需要从5.6追踪6.13试验，再回指6.5特定载荷和速度基准，属于真实三段关系链。",
    },
    {
        "id": "gb_multi_hop_009", "task_type": "multi_hop_relation",
        "question": "哪些碰撞预警和紧急制动试验可用仿真替代，使用的工具链还必须满足什么可信度要求？",
        "answer": {"substitutable_tests": ["6.5", "6.6", "6.7", "6.8", "6.9", "6.10"], "toolchain_requirement": "按附录B验证、确认并按规定使用", "credibility_dimensions": ["能力", "准确性", "正确性", "适用性", "可用性"]},
        "claims": [claim("6.5至6.10的碰撞预警和紧急制动试验可通过仿真开展。", "gb39901:clause:6.14"), claim("仿真工具链必须按附录B验证和确认。", "gb39901:clause:6.14"), claim("仿真工具链必须按附录B的规定使用。", "gb39901:clause:6.14"), claim("可信度证明覆盖工具链的能力以及能力不足。", "gb39901:appendix:B.2"), claim("可信度证明覆盖工具链复现场地试验目标数据的准确性。", "gb39901:appendix:B.2"), claim("可信度证明覆盖工具链数据和算法的正确性。", "gb39901:appendix:B.2"), claim("可信度证明覆盖工具链在有效域内对评估内容的适用性。", "gb39901:appendix:B.2"), claim("可信度证明覆盖所需培训、经验和工具链管理流程的可用性。", "gb39901:appendix:B.2")],
        "evidence": ["gb39901:clause:6.14", "gb39901:appendix:B.2"],
        "steps": [("Requirement", "允许以仿真执行部分法规试验", "gb39901:clause:6.14"), ("TestSet", "6.5至6.10", "gb39901:clause:6.14"), ("Toolchain", "附录B仿真试验工具链", "gb39901:appendix:B.2"), ("CredibilityRequirement", "能力、准确性、正确性、适用性、可用性", "gb39901:appendix:B.2")],
        "reason": "可替代范围在6.14，工具链可信度维度在附录B.2，无法由单段文本完整回答。",
        "scoring": "claim_f1",
    },
    {
        "id": "gb_multi_hop_010", "task_type": "multi_hop_relation",
        "question": "部分采用仿真完成6.5至6.10试验时，同一速度和载荷项目至少需要几次场地试验？仿真与场地结论不一致时第三次应是什么试验？",
        "answer": {"scope": "6.5至6.10部分采用仿真", "grouping_key": ["同一试验车辆速度", "同一试验车辆载荷"], "minimum_field_tests": 1, "disagreement_third_test": "场地试验"},
        "claims": [claim("同一试验车辆速度和载荷组成的项目至少包括一次场地试验。", "gb39901:clause:6.14"), claim("仿真与场地试验的合规判定不一致时，第3次试验应为场地试验。", "gb39901:clause:6.14")],
        "evidence": ["gb39901:clause:6.14"],
        "steps": [("Requirement", "部分试验采用仿真", "gb39901:clause:6.14"), ("GroupingCondition", "同一试验车辆速度和载荷", "gb39901:clause:6.14"), ("MinimumEvidence", "至少一次场地试验", "gb39901:clause:6.14"), ("DisagreementRule", "第3次必须为场地试验", "gb39901:clause:6.14")],
        "reason": "同一条款内存在分支决策链，问题要求同时恢复分组键、最低实测量与冲突处理规则。",
    },
    {
        "id": "gb_multi_hop_011", "task_type": "multi_hop_relation",
        "question": "附录A中“非预期的侧向运动”对应什么 ASIL 等级、安全目标和安全度量？",
        "answer": {"hazard": "非预期的侧向运动", "asil": "D", "safety_goal": "避免系统非预期激活、过大制动力或制动力不均衡导致车辆失稳，并符合相应安全度量", "safety_metrics": ["侧向加速度变化值或最大值不超过安全阈值", "侧向位移不超过安全阈值", "横摆角速度变化值不超过安全阈值"]},
        "claims": [claim("非预期的侧向运动对应ASIL D。", "gb39901:appendix:A.2.3"), claim("安全目标是避免非预期激活、过大或不均衡制动力导致车辆失稳。", "gb39901:appendix:A.2.3"), claim("安全度量涵盖侧向加速度、侧向位移和横摆角速度变化不超过安全阈值。", "gb39901:appendix:A.2.3")],
        "evidence": ["gb39901:appendix:A.2.3"],
        "steps": [("Hazard", "非预期的侧向运动", "gb39901:appendix:A.2.3"), ("ASIL", "D", "gb39901:appendix:A.2.3"), ("SafetyGoal", "避免非预期侧向运动导致车辆失稳", "gb39901:appendix:A.2.3"), ("SafetyMetricSet", "侧向加速度、位移、横摆角速度阈值", "gb39901:appendix:A.2.3")],
        "reason": "需要按表A.1同一行恢复危害—ASIL—安全目标—三项安全度量关系，不能只返回等级。",
        "scoring": "claim_f1",
    },
    {
        "id": "gb_multi_hop_012", "task_type": "multi_hop_relation",
        "question": "附录A如何通过故障注入验证功能安全概念，验证对象、注入时机和目的分别是什么？",
        "answer": {"method": "向电子电气或机械组件施加输入以模拟组件内部故障", "targets": ["电子电气组件", "机械组件"], "injection_timing": ["系统激活前", "系统激活状态下"], "purposes": ["确认单个组件失效时的反应", "验证可能导致整车危害的故障被安全措施有效覆盖", "验证系统及整车实现功能安全要求和安全目标"], "test_reference": "表A.2"},
        "claims": [claim("通过向电子电气或机械组件施加输入模拟内部故障。", "gb39901:appendix:A.3.3"), claim("故障在系统激活前或激活状态下注入。", "gb39901:appendix:A.3.3"), claim("目的是确认组件失效反应、验证安全措施覆盖并实现功能安全要求和目标，且按表A.2开展。", "gb39901:appendix:A.3.3")],
        "evidence": ["gb39901:appendix:A.3.3"],
        "steps": [("SafetyConcept", "功能安全概念", "gb39901:appendix:A.3.3"), ("VerificationMethod", "组件故障输入与故障注入", "gb39901:appendix:A.3.3"), ("Condition", "激活前或激活状态下注入", "gb39901:appendix:A.3.3"), ("AcceptancePurpose", "安全措施覆盖且实现安全目标", "gb39901:appendix:A.3.3")],
        "reason": "需要连接安全概念、组件、故障注入时机、覆盖验证和安全目标，属于功能安全关系链。",
        "scoring": "claim_f1",
    },
    {
        "id": "gb_compare_001", "task_type": "comparison_exception",
        "question": "M1 与 N1 对前方车辆目标的最低激活速度范围有何不同？对行人、自行车和踏板式两轮摩托车目标是否相同？",
        "answer": {"vehicle_target": {"M1": [10, 80], "N1": [10, 60], "unit": "km/h"}, "VRU_targets": {"M1_and_N1": [20, 60], "unit": "km/h", "targets": ["行人", "自行车", "踏板式两轮摩托车"]}},
        "claims": [claim("前方车辆目标下M1至少覆盖10至80 km/h，N1至少覆盖10至60 km/h。", "gb39901:clause:4.1"), claim("行人、自行车和踏板式两轮摩托车目标下，两类车均至少覆盖20至60 km/h。", "gb39901:clause:4.1")],
        "evidence": ["gb39901:clause:4.1"],
        "steps": [("Requirement", "AEBS激活速度范围", "gb39901:clause:4.1"), ("VehicleCategory", "M1与N1", "gb39901:clause:4.1"), ("TargetType", "车辆目标与三类弱势目标", "gb39901:clause:4.1"), ("Comparison", "车辆目标上限不同，弱势目标范围相同", "gb39901:clause:4.1")],
        "reason": "必须在同一规则树中按车型与目标类型交叉比较，避免把车辆目标上限错误泛化到弱势目标。",
        "scoring": "claim_f1",
    },
    {
        "id": "gb_compare_002", "task_type": "comparison_exception",
        "question": "6.5至6.10与6.11至6.13的试验车辆载荷要求有何不同？行车质量大于最大设计总质量时如何处理？",
        "answer": {"tests_6.5_to_6.10": ["行车质量", "最大设计总质量"], "tests_6.11_to_6.13": ["最大设计总质量"], "exception": "若行车质量大于最大设计总质量，以最大设计总质量替代原行车质量条件，原总质量条件不变"},
        "claims": [claim("6.5至6.10分别以行车质量和最大设计总质量试验。", "gb39901:clause:6.1.1"), claim("6.11至6.13仅以最大设计总质量试验。", "gb39901:clause:6.1.1"), claim("行车质量大于最大设计总质量时，用最大设计总质量替代原行车质量条件。", "gb39901:clause:6.1.1"), claim("行车质量大于最大设计总质量时，原最大设计总质量试验不变。", "gb39901:clause:6.1.1")],
        "evidence": ["gb39901:clause:6.1.1"],
        "steps": [("TestSet", "6.5至6.10", "gb39901:clause:6.1.1"), ("LoadState", "行车质量和最大设计总质量", "gb39901:clause:6.1.1"), ("TestSet", "6.11至6.13", "gb39901:clause:6.1.1"), ("Exception", "行车质量超总质量时以总质量替代", "gb39901:clause:6.1.1")],
        "reason": "要求比较两个试验集合并保留反常质量关系的替代规则。",
        "scoring": "claim_f1",
    },
    {
        "id": "gb_compare_003", "task_type": "comparison_exception",
        "question": "若驾驶员可调系统激活时机，6.11误响应试验与其余规定试验的设置有何相反要求？",
        "answer": {"earliest_activation": ["6.11"], "latest_activation": ["6.5", "6.6", "6.7", "6.8", "6.9", "6.10", "6.12", "6.13"]},
        "claims": [claim("6.11误响应试验选择最早激活时机。", "gb39901:clause:6.1.2.2"), claim("6.5至6.10和6.12至6.13选择最晚激活时机。", "gb39901:clause:6.1.2.2")],
        "evidence": ["gb39901:clause:6.1.2.2"],
        "steps": [("AdjustableSetting", "驾驶员可调激活时机", "gb39901:clause:6.1.2.2"), ("TestSet", "6.11误响应试验", "gb39901:clause:6.1.2.2"), ("Comparison", "最早激活对比其他试验最晚激活", "gb39901:clause:6.1.2.2")],
        "reason": "最早/最晚方向相反，要求将试验编号集合映射到正确设置。",
        "scoring": "claim_f1",
    },
    {
        "id": "gb_compare_004", "task_type": "comparison_exception",
        "question": "6.5至6.7车辆目标试验与其他试验的最低光照强度分别是多少？",
        "answer": {"tests_6.5_to_6.7": {"minimum": 1000, "unit": "lx"}, "other_tests": {"minimum": 2000, "unit": "lx"}},
        "claims": [claim("6.5至6.7试验光照强度不小于1000 lx。", "gb39901:clause:6.4"), claim("其他试验光照强度不小于2000 lx。", "gb39901:clause:6.4")],
        "evidence": ["gb39901:clause:6.4"],
        "steps": [("EnvironmentRequirement", "试验光照强度", "gb39901:clause:6.4"), ("TestSet", "6.5至6.7车辆目标试验", "gb39901:clause:6.4"), ("Comparison", "1000 lx对其他试验2000 lx", "gb39901:clause:6.4")],
        "reason": "测试集合和阈值成对对应，容易把2000 lx错误应用到所有试验。",
    },
    {
        "id": "gb_compare_005", "task_type": "comparison_exception",
        "question": "车辆目标、儿童行人、自行车和踏板式两轮摩托车试验的最低通过率如何分组？",
        "answer": {"minimum_pass_rate_percent": {"车辆目标": 90, "儿童行人": 90, "自行车": 80, "踏板式两轮摩托车": 80}},
        "claims": [claim("车辆目标和儿童行人试验的通过次数占比均不小于90%。", "gb39901:clause:5.3"), claim("自行车和踏板式两轮摩托车试验的通过次数占比均不小于80%。", "gb39901:clause:5.3")],
        "evidence": ["gb39901:clause:5.3"],
        "steps": [("RobustnessRequirement", "系统鲁棒性", "gb39901:clause:5.3"), ("TargetGroup", "车辆和儿童行人", "gb39901:clause:5.3"), ("Threshold", "通过率>=90%", "gb39901:clause:5.3"), ("Comparison", "自行车和摩托车通过率>=80%", "gb39901:clause:5.3")],
        "reason": "需要完整映射四类目标与两档通过率，不能只返回一个百分比。",
        "scoring": "claim_f1",
    },
    {
        "id": "gb_compare_006", "task_type": "comparison_exception",
        "question": "新申请型式批准与已获型式批准的 M1 类汽车（含多用途货车）在一般要求和踏板式两轮摩托车要求上的实施节奏有何不同？",
        "answer": {"new_M1_general": "实施之日起", "approved_M1_general": "实施之日起第13个月", "new_and_approved_M1_PTW": "实施之日起第25个月"},
        "claims": [claim("新申请M1及多用途货车的一般要求自实施之日起执行。", "gb39901:clause:9"), claim("已获批准M1及多用途货车的一般要求从第13个月执行。", "gb39901:clause:9"), claim("两者的踏板式两轮摩托车相关要求均从第25个月执行。", "gb39901:clause:9")],
        "evidence": ["gb39901:clause:9"],
        "steps": [("ImplementationRule", "M1分阶段实施", "gb39901:clause:9"), ("ApprovalState", "新申请与已获批准", "gb39901:clause:9"), ("RequirementGroup", "一般要求与摩托车要求", "gb39901:clause:9"), ("Timeline", "0/13/25个月", "gb39901:clause:9")],
        "reason": "需沿车型—批准状态—要求组—月份四维关系比较，PTW是共同例外。",
        "scoring": "claim_f1",
    },
    {
        "id": "gb_compare_007", "task_type": "comparison_exception",
        "question": "除多用途货车外的 N1 类汽车，新申请型式批准与已获型式批准车辆分别从第几个月执行？新申请车辆的摩托车目标要求是否另有延后？",
        "answer": {"new_N1_general": "实施之日起第13个月", "new_N1_PTW": "实施之日起第25个月", "approved_N1_all": "实施之日起第25个月"},
        "claims": [claim("新申请的非多用途货车N1一般要求从第13个月执行，摩托车相关要求从第25个月执行。", "gb39901:clause:9"), claim("已获批准的非多用途货车N1从第25个月执行。", "gb39901:clause:9")],
        "evidence": ["gb39901:clause:9"],
        "steps": [("ImplementationRule", "非多用途货车N1分阶段实施", "gb39901:clause:9"), ("ApprovalState", "新申请与已获批准", "gb39901:clause:9"), ("Exception", "新申请PTW要求延至25个月", "gb39901:clause:9")],
        "reason": "需区分N1是否多用途货车、批准状态和PTW例外，防止套用M1时间表。",
        "scoring": "claim_f1",
    },
    {
        "id": "gb_compare_008", "task_type": "comparison_exception",
        "question": "一般性能试验与功能安全相关文档检验/试验的同一型式判定分别依据8.1还是8.2，核心条件有何不同？",
        "answer": {"general_tests": {"clause": "8.1", "conditions": ["AEB系统配置", "相关车辆参数", "制动系统配置", "制动电子控制系统型号"]}, "functional_safety": {"clause": "8.2", "conditions": ["系统型号、生产企业及软件版本规则", "系统功能安全描述相同且符合附录C"]}},
        "claims": [claim("除功能安全与电磁兼容等排除项外的一般相关试验按8.1的系统、车辆和制动配置条件判定。", "gb39901:clause:8"), claim("4.5、附录A和附录C的功能安全相关检验试验按8.2，以系统身份规则和功能安全描述相同为核心。", "gb39901:clause:8")],
        "evidence": ["gb39901:clause:8"],
        "steps": [("TypeApproval", "同一型式判定", "gb39901:clause:8"), ("TestCategory", "一般性能试验与功能安全试验", "gb39901:clause:8"), ("ClauseMapping", "8.1与8.2", "gb39901:clause:8"), ("ConditionSet", "配置参数对比功能安全描述", "gb39901:clause:8")],
        "reason": "需要先按试验性质分流，再映射两套不同条件集合。",
        "scoring": "claim_f1",
    },
    {
        "id": "gb_synthesis_001", "task_type": "cross_section_synthesis",
        "question": "完整列出6.11规定的五类误响应场景，并说明所有场景共同的合格判据。",
        "answer": {"scenarios": ["车辆跟车过程中车辆目标右转", "相邻车道静止车辆目标", "车道内铁板", "车辆直行经过同向运动的成年行人目标", "车辆直行经过对向静止的自行车目标"], "common_acceptance": "系统不发出碰撞预警且不实施紧急制动"},
        "claims": [claim("误响应场景包括跟车过程中车辆目标右转。", "gb39901:clause:6.11"), claim("误响应场景包括相邻车道静止车辆目标。", "gb39901:clause:6.11"), claim("误响应场景包括车道内铁板。", "gb39901:clause:6.11"), claim("误响应场景包括同向运动的成年行人。", "gb39901:clause:6.11"), claim("误响应场景包括对向静止的自行车。", "gb39901:clause:6.11"), claim("所有场景共同要求不发出碰撞预警和紧急制动。", "gb39901:clause:5.4")],
        "evidence": ["gb39901:clause:5.4", "gb39901:clause:6.11"],
        "steps": [("Requirement", "不存在碰撞危险时避免误响应", "gb39901:clause:5.4"), ("TestSuite", "6.11误响应试验", "gb39901:clause:6.11"), ("ScenarioSet", "6.11.1至6.11.5五类场景", "gb39901:clause:6.11"), ("AcceptanceCriterion", "不预警且不紧急制动", "gb39901:clause:5.4")],
        "reason": "答案横跨总性能判据和五个分散的子试验，考查完整枚举与共同关系汇总。",
        "scoring": "claim_f1",
    },
    {
        "id": "gb_synthesis_002", "task_type": "cross_section_synthesis",
        "question": "车辆产品使用说明书至少要覆盖哪些 AEBS 信息？请完整枚举。",
        "answer": {"items": ["系统功能描述，含能力、运行速度区间、可识别目标和待机/激活条件", "系统开启、关闭和驾驶员干预方式", "系统警告信号及提示信号说明", "系统能力不足或使用限制说明"]},
        "claims": [claim("说明书应包含系统能力、速度区间、目标类型和待机激活条件等功能描述。", "gb39901:clause:7"), claim("说明书应包含系统开启、关闭和驾驶员干预方式。", "gb39901:clause:7"), claim("说明书应包含警告及提示信号说明。", "gb39901:clause:7"), claim("说明书应包含能力不足或使用限制。", "gb39901:clause:7")],
        "evidence": ["gb39901:clause:7"],
        "steps": [("DocumentRequirement", "产品使用说明书", "gb39901:clause:7"), ("ContentGroup", "功能与条件", "gb39901:clause:7"), ("ContentGroup", "操作与干预", "gb39901:clause:7"), ("ContentGroup", "信号与使用限制", "gb39901:clause:7")],
        "reason": "虽来自一个章节，但四组内容需完整枚举，遗漏任一组即扣召回。",
        "scoring": "set_f1",
    },
    {
        "id": "gb_synthesis_003", "task_type": "cross_section_synthesis",
        "question": "附录A.2.1区分的“提交文档”和“备查文档”分别有哪些？",
        "answer": {"submitted": ["系统描述", "危害分析和风险评估总结", "安全措施说明", "整车层面的安全分析总结", "系统层面的安全分析总结", "针对误响应的安全分析总结", "系统层面的验证计划和结果总结", "整车层面的验证确认计划和结果总结"], "retained_for_inspection": ["详细危害分析和风险评估", "详细整车层面的安全分析", "详细系统层面的安全分析", "详细系统层面的验证计划和结果", "详细整车层面的验证确认计划和结果", "其他支撑性材料或数据（若有）"]},
        "claims": [claim("提交文档共有八类，涵盖系统描述、风险总结、安全措施、两级安全分析总结、误响应分析总结和两级验证总结。", "gb39901:appendix:A.2.1"), claim("备查文档共有六类，涵盖详细风险分析、两级详细安全分析、两级详细验证结果及其他材料。", "gb39901:appendix:A.2.1")],
        "evidence": ["gb39901:appendix:A.2.1"],
        "steps": [("DocumentFramework", "A.2功能安全文档", "gb39901:appendix:A.2.1"), ("DocumentSet", "提交文档八类", "gb39901:appendix:A.2.1"), ("DocumentSet", "备查文档六类", "gb39901:appendix:A.2.1")],
        "reason": "需要区分提交与备查两个集合并保持14个条目的归属，适合集合级图检索。",
        "scoring": "claim_f1",
    },
    {
        "id": "gb_synthesis_004", "task_type": "cross_section_synthesis",
        "question": "仿真试验工具链的可信度证明包括哪些维度，且验证和确认阶段分别要解决什么问题？",
        "answer": {"credibility_dimensions": ["能力", "准确性", "正确性", "适用性", "可用性"], "verification": ["准确表示系统相关性能", "证明功能建模正确实现", "数值误差合理", "识别关键参数并鲁棒校准"], "validation": ["用物理试验证明工具链准确代表系统", "满足KPI与相关性阈值", "量化不确定性并设置安全裕度", "必要时接受额外场地确认试验"]},
        "claims": [claim("可信度维度包括能力、准确性、正确性、适用性和可用性。", "gb39901:appendix:B.2"), claim("验证关注模型正确实现、性能表示、数值误差和关键参数。", "gb39901:appendix:B.2"), claim("确认关注物理与仿真可比、KPI相关性阈值、不确定性以及额外场地试验。", "gb39901:appendix:B.2")],
        "evidence": ["gb39901:appendix:B.2"],
        "steps": [("CredibilityFramework", "仿真工具链可信度", "gb39901:appendix:B.2"), ("DimensionSet", "五项总体维度", "gb39901:appendix:B.2"), ("Verification", "正确实现与误差控制", "gb39901:appendix:B.2"), ("Validation", "物理可比、阈值与不确定性", "gb39901:appendix:B.2")],
        "reason": "需在附录B多个子节间区分总体维度、verification和validation，关键词相近但职责不同。",
        "scoring": "claim_f1",
    },
    {
        "id": "gb_synthesis_005", "task_type": "cross_section_synthesis",
        "question": "附录C要求系统功能安全描述至少覆盖哪些主类内容？系统描述内部又应覆盖哪些方面？",
        "answer": {"main_sections": ["系统描述", "危害分析和风险评估总结", "安全措施说明", "其他要求"], "system_description": ["系统功能", "范围、边界和接口", "运行条件、约束限制和有效工作范围", "整车布置及外观", "组件清单及软硬件识别", "内外机械、电气、信号连接", "信号流、运行数据和优先顺序"]},
        "claims": [claim("功能安全描述主类包括系统描述、危害分析和风险评估总结、安全措施说明及其他要求。", "gb39901:appendix:C.2"), claim("系统描述覆盖功能、边界接口、运行限制、布置外观、组件清单、连接和信号流优先顺序。", "gb39901:appendix:C.2")],
        "evidence": ["gb39901:appendix:C.2"],
        "steps": [("Document", "系统功能安全描述", "gb39901:appendix:C.2"), ("SectionSet", "C.2四类主内容", "gb39901:appendix:C.2"), ("Section", "C.2.1系统描述", "gb39901:appendix:C.2"), ("SubsectionSet", "功能、边界、限制、布置、组件、连接与信号流", "gb39901:appendix:C.2")],
        "reason": "需要恢复附录C的层级结构及系统描述的七类子内容，而非平铺关键词。",
        "scoring": "claim_f1",
    },
    {
        "id": "gb_synthesis_006", "task_type": "cross_section_synthesis",
        "question": "从危害识别到最终验证结论，附录A规定的功能安全证据闭环是什么？",
        "answer": {"stages": ["A.2.3危害分析与风险评估，形成危害、ASIL和安全目标", "A.2.4定义实现安全目标的安全措施", "A.2.5在整车和系统层面开展安全分析并处理故障", "A.2.6制定并保存系统及整车验证确认计划和结果", "A.3按文档实施功能与功能安全验证，包括故障注入", "A.3.4确认结果与计划一致并说明充分性和有效性"]},
        "claims": [claim("闭环从危害、ASIL和安全目标识别开始，再定义安全措施。", "gb39901:appendix:A.2-A.3"), claim("随后通过整车/系统安全分析与验证确认计划形成证据。", "gb39901:appendix:A.2-A.3"), claim("最终实施功能和故障注入验证，结论说明概念与实施效果的充分性和有效性。", "gb39901:appendix:A.2-A.3")],
        "evidence": ["gb39901:appendix:A.2-A.3"],
        "steps": [("HazardAnalysis", "A.2.3危害与安全目标", "gb39901:appendix:A.2-A.3"), ("SafetyMeasure", "A.2.4安全措施", "gb39901:appendix:A.2-A.3"), ("SafetyAnalysis", "A.2.5整车与系统分析", "gb39901:appendix:A.2-A.3"), ("VerificationPlan", "A.2.6验证确认计划和结果", "gb39901:appendix:A.2-A.3"), ("Verification", "A.3功能与故障注入验证", "gb39901:appendix:A.2-A.3"), ("Conclusion", "A.3.4充分性与有效性结论", "gb39901:appendix:A.2-A.3")],
        "reason": "答案跨越附录A六个连续阶段，图结构应支持顺序与产物关系的整体召回。",
        "scoring": "claim_f1",
    },
    {
        "id": "gb_unanswerable_001", "task_type": "unanswerable_adversarial", "answerable": False,
        "question": "制造商能否完全用仿真替代6.11的五项误响应试验？如果可以，需要满足哪些条件？",
        "answer": {"answerable": False, "reason": "不能从标准推出。6.14仅授权6.5至6.10通过仿真开展，没有授权6.11误响应试验由仿真完全替代。"},
        "claims": [], "evidence": ["gb39901:clause:6.14", "gb39901:clause:6.11"],
        "steps": [("ClaimBoundary", "仿真替代授权范围", "gb39901:clause:6.14"), ("AuthorizedTestSet", "仅6.5至6.10", "gb39901:clause:6.14"), ("ExcludedQuestion", "6.11误响应试验", "gb39901:clause:6.11")],
        "reason": "边界证据明确列出仿真授权范围，6.11在范围之外；正确行为是拒绝补造许可条件。",
    },
    {
        "id": "gb_unanswerable_002", "task_type": "unanswerable_adversarial", "answerable": False,
        "question": "N1 类汽车以80 km/h驶向静止车辆目标、最大设计总质量状态时，表2规定的最大相对碰撞速度是多少？",
        "answer": {"answerable": False, "reason": "表2没有80 km/h的N1试验行，且N1车辆目标激活范围至少仅到60 km/h，无法从该表得出80 km/h阈值。"},
        "claims": [], "evidence": ["gb39901:table:2", "gb39901:clause:4.1"],
        "steps": [("Table", "表2 N1静止车辆目标", "gb39901:table:2"), ("MaximumListedCondition", "最高列至60 km/h", "gb39901:table:2"), ("UnsupportedCondition", "80 km/h", "gb39901:clause:4.1")],
        "reason": "近似表格诱导题；不得外推60 km/h行或套用M1的80 km/h阈值。",
    },
    {
        "id": "gb_unanswerable_003", "task_type": "unanswerable_adversarial", "answerable": False,
        "question": "所有车型和系统方案的五类危害都必须固定采用表A.1所列的同一ASIL等级吗？请给出不可变的等级表。",
        "answer": {"answerable": False, "reason": "不存在不可变的通用等级表。制造商可定义更高ASIL；有外部措施时可降低并提供说明，因此不能将表A.1无条件固定到所有方案。"},
        "claims": [], "evidence": ["gb39901:appendix:A.2.3"],
        "steps": [("RiskAssessment", "表A.1危害与ASIL", "gb39901:appendix:A.2.3"), ("Exception", "可采用更高ASIL", "gb39901:appendix:A.2.3"), ("Exception", "有外部措施可降低并说明", "gb39901:appendix:A.2.3")],
        "reason": "问题含错误的“不可变”前提；边界脚注明示等级可因风险评估和外部措施调整。",
    },
    {
        "id": "gb_unanswerable_004", "task_type": "unanswerable_adversarial", "answerable": False,
        "question": "表A.1规定非预期减速的最大纵向减速度安全阈值精确为多少m/s²？",
        "answer": {"answerable": False, "reason": "标准未给统一数值。它只要求不超过安全阈值，并说明安全阈值可按车型、系统方案和实车测试结果由制造商定义。"},
        "claims": [], "evidence": ["gb39901:appendix:A.2.3"],
        "steps": [("Hazard", "非预期的减速", "gb39901:appendix:A.2.3"), ("SafetyMetric", "最大纵向减速度不超过安全阈值", "gb39901:appendix:A.2.3"), ("MissingValue", "标准无统一m/s²数值", "gb39901:appendix:A.2.3")],
        "reason": "检验模型能否区分性能条款中的5.0 m/s²与功能安全中由制造商定义的安全阈值。",
    },
    {
        "id": "gb_unanswerable_005", "task_type": "unanswerable_adversarial", "answerable": False,
        "question": "探测到导致系统不可用的电子电气故障后，标准要求必须在精确多少秒内发出故障警告？",
        "answer": {"answerable": False, "reason": "条款只规定“不应延迟发出”，没有给出可用于精确计时的秒数。"},
        "claims": [], "evidence": ["gb39901:clause:4.3.2.2"],
        "steps": [("Fault", "可探测的电子电气故障", "gb39901:clause:4.3.2.2"), ("TimingRequirement", "不应延迟发出警告", "gb39901:clause:4.3.2.2"), ("MissingValue", "未规定秒数", "gb39901:clause:4.3.2.2")],
        "reason": "“不应延迟”是定性时机要求，不能臆造具体秒数。",
    },
    {
        "id": "gb_unanswerable_006", "task_type": "unanswerable_adversarial", "answerable": False,
        "question": "GB 39901—2025是否强制每套AEBS同时安装摄像头、毫米波雷达和激光雷达各一个？",
        "answer": {"answerable": False, "reason": "标准没有强制这一固定硬件组合。3.12仅将传感器、控制器和执行器作为通常组件，相关条款中的摄像头、雷达等也是示例或按实际系统配置分析。"},
        "claims": [], "evidence": ["gb39901:clause:3.12", "gb39901:clause:4.2", "gb39901:appendix:A.3.3"],
        "steps": [("Definition", "电子控制系统通常组件", "gb39901:clause:3.12"), ("SelfCheckRequirement", "检查相关传感元件", "gb39901:clause:4.2"), ("UnsupportedPremise", "无固定三传感器组合", "gb39901:appendix:A.3.3")],
        "reason": "问题把示例组件误读为强制BOM；正确回答必须拒绝该硬件前提。",
    },
    {
        "id": "cross_align_001", "task_type": "cross_document_alignment",
        "question": "GB 39901—2025与UNECE R152对系统长时间未完成初始化的提示条件是否一致？比较车速、累计时间、提示和持续条件。",
        "answer": {"common_condition": {"speed_operator": ">", "speed": 10, "speed_unit": "km/h", "cumulative_time": 15, "time_unit": "s", "state": "仍未完成初始化"}, "GB39901": "至少发出光学警告并持续至初始化完成", "UNECE_R152": "向驾驶员指示该状态并持续至成功初始化", "assessment": "数值条件一致，提示表述粒度不同"},
        "claims": [claim("GB要求车速大于10 km/h且累计行驶15 s后仍未初始化时发光学警告至初始化完成。", "gb39901:clause:4.3.2.1"), claim("UNECE要求在高于10 km/h累计驾驶15 s后仍未初始化时向驾驶员指示，直至成功初始化。", "unece_r152:clause:5.1.4.1.2"), claim("两者数值条件一致，但GB明确至少为光学警告，UNECE表述为状态信息。", "gb39901:clause:4.3.2.1", "unece_r152:clause:5.1.4.1.2")],
        "evidence": ["gb39901:clause:4.3.2.1", "unece_r152:clause:5.1.4.1.2"],
        "steps": [("Requirement", "GB初始化未完成警告", "gb39901:clause:4.3.2.1"), ("Alignment", "车速>10 km/h且累计15 s", ["gb39901:clause:4.3.2.1", "unece_r152:clause:5.1.4.1.2"]), ("Requirement", "UNECE初始化状态信息", "unece_r152:clause:5.1.4.1.2"), ("Comparison", "数值一致、提示形式表述不同", ["gb39901:clause:4.3.2.1", "unece_r152:clause:5.1.4.1.2"])],
        "reason": "需跨两份法规对齐条件元组，再识别警告形式的语义差异。",
        "scoring": "claim_f1",
    },
    {
        "id": "cross_align_002", "task_type": "cross_document_alignment",
        "question": "GB 39901—2025与UNECE R152的车辆目标碰撞预警时机如何对齐？两者的0.8 s规则和例外条件是否完全相同？",
        "answer": {"common_rule": "通常最迟在紧急制动开始前0.8 s发出预警", "GB_exception": "若未发生碰撞，最迟可与紧急制动同时发出", "UNECE_exception": "若无法及时预见碰撞以提前0.8 s预警，最迟可在紧急制动开始时发出", "assessment": "默认阈值一致，例外触发条件措辞不完全相同"},
        "claims": [claim("两份文件的通常规则均为预警最迟提前紧急制动0.8 s。", "gb39901:clause:5.1.1", "unece_r152:clause:5.2.1.1"), claim("GB例外以未发生碰撞为条件。", "gb39901:clause:5.1.1"), claim("UNECE例外以无法及时预见并提前0.8 s预警为条件。", "unece_r152:clause:5.2.1.1")],
        "evidence": ["gb39901:clause:5.1.1", "unece_r152:clause:5.2.1.1"],
        "steps": [("Requirement", "GB车辆目标预警时机", "gb39901:clause:5.1.1"), ("Alignment", "默认提前0.8 s", ["gb39901:clause:5.1.1", "unece_r152:clause:5.2.1.1"]), ("Requirement", "UNECE车辆目标预警时机", "unece_r152:clause:5.2.1.1"), ("ExceptionComparison", "未碰撞对无法及时预见", ["gb39901:clause:5.1.1", "unece_r152:clause:5.2.1.1"])],
        "reason": "简单数值相同但例外语义不同，必须分别绑定两份法规后才能避免错误宣称完全等价。",
        "scoring": "claim_f1",
    },
    {
        "id": "cross_align_003", "task_type": "cross_document_alignment",
        "question": "GB 39901—2025、UNECE R152和Euro NCAP C2C协议对车辆目标及ISO 19206-3的使用如何对应？",
        "answer": {"GB39901": "车辆目标可符合ISO 19206-3，或使用大批量生产普通乘用车", "UNECE_R152": "可使用量产M1乘用车，或符合ISO 19206-3:2020的软目标", "Euro_NCAP": "使用GVT，推进系统与GVT组合应符合ISO 19206-3:2021以保证可重复性", "assessment": "三者共享ISO 19206-3目标体系，但法规保留量产车替代，版本和强制使用方式不同"},
        "claims": [claim("GB允许ISO 19206-3车辆目标或量产普通乘用车。", "gb39901:clause:6.3"), claim("UNECE允许量产M1乘用车或ISO 19206-3:2020软目标。", "unece_r152:clause:6.3.1"), claim("Euro NCAP使用GVT并要求推进系统与GVT组合满足ISO 19206-3:2021。", "euroncap_c2c:clause:5.1")],
        "evidence": ["gb39901:clause:6.3", "unece_r152:clause:6.3.1", "euroncap_c2c:clause:5.1"],
        "steps": [("Standard", "GB 39901车辆目标", "gb39901:clause:6.3"), ("Alignment", "ISO 19206-3目标体系", ["gb39901:clause:6.3", "unece_r152:clause:6.3.1"]), ("Standard", "UNECE R152软目标或量产车", "unece_r152:clause:6.3.1"), ("Protocol", "Euro NCAP GVT与ISO 19206-3:2021", "euroncap_c2c:clause:5.1")],
        "reason": "需要跨三文档对齐目标物概念，同时保留版本号和“可替代/必须使用”的制度差异。",
        "scoring": "claim_f1",
    },
    {
        "id": "cross_align_004", "task_type": "cross_document_alignment",
        "question": "将GB 39901的6.5、6.6、6.7车辆目标试验映射到Euro NCAP的CCRs、CCRm、CCRb，分别如何对应？",
        "answer": {"mapping": {"GB 6.5 静止车辆目标": "CCRs", "GB 6.6 匀速车辆目标": "CCRm", "GB 6.7 制动车辆目标": "CCRb"}},
        "claims": [claim("GB 6.5静止车辆目标对应CCRs。", "gb39901:clause:6.5-6.7", "euroncap_c2c:clause:2.2"), claim("GB 6.6匀速车辆目标对应CCRm。", "gb39901:clause:6.5-6.7", "euroncap_c2c:clause:2.2"), claim("GB 6.7制动车辆目标对应CCRb。", "gb39901:clause:6.5-6.7", "euroncap_c2c:clause:2.2")],
        "evidence": ["gb39901:clause:6.5-6.7", "euroncap_c2c:clause:2.2"],
        "steps": [("TestSet", "GB 6.5至6.7车辆目标试验", "gb39901:clause:6.5-6.7"), ("ScenarioSemantics", "静止、匀速、制动", ["gb39901:clause:6.5-6.7", "euroncap_c2c:clause:2.2"]), ("ProtocolScenarioSet", "CCRs、CCRm、CCRb", "euroncap_c2c:clause:2.2")],
        "reason": "映射不靠编号相似，而靠目标运动状态语义跨文档匹配。",
        "scoring": "claim_f1",
    },
    {
        "id": "cross_compare_001", "task_type": "cross_document_comparison",
        "question": "GB 39901—2025与UNECE R152在适用车型和碰撞目标范围上有何共同点与差异？",
        "answer": {"common_vehicle_categories": ["M1", "N1"], "common_targets": ["前方乘用车", "行人", "自行车"], "GB_additional_target": "踏板式两轮摩托车", "UNECE_scope_evidence_for_PTW": "所引范围未包含"},
        "claims": [claim("两份法规均适用于M1和N1，并覆盖前车、行人和自行车。", "gb39901:clause:1", "gb39901:clause:4.1", "unece_r152:clause:1"), claim("GB还明确覆盖踏板式两轮摩托车，UNECE R152范围条款未列该目标。", "gb39901:clause:4.1", "unece_r152:clause:1")],
        "evidence": ["gb39901:clause:1", "gb39901:clause:4.1", "unece_r152:clause:1"],
        "steps": [("Standard", "GB 39901范围", ["gb39901:clause:1", "gb39901:clause:4.1"]), ("CommonScope", "M1/N1及车、行人、自行车", ["gb39901:clause:4.1", "unece_r152:clause:1"]), ("Standard", "UNECE R152范围", "unece_r152:clause:1"), ("Difference", "GB额外含踏板式两轮摩托车", ["gb39901:clause:4.1", "unece_r152:clause:1"])],
        "reason": "必须在两份范围证据上做集合交集和差集，不能把“未列出”误说成明文禁止。",
        "scoring": "claim_f1",
    },
    {
        "id": "cross_compare_002", "task_type": "cross_document_comparison",
        "question": "GB 39901—2025与UNECE R152对AEBS的定义在核心功能和表述侧重点上有何异同？",
        "answer": {"common": ["面向即将发生的前向碰撞", "自动激活车辆制动使车辆减速", "目的为避免或减轻碰撞"], "GB_emphasis": ["实时监测车辆前方行驶环境", "发出警告信号并自动制动"], "UNECE_emphasis": ["自动探测即将发生的前向碰撞", "定义本身未把警告作为AEBS定义的必备动作"]},
        "claims": [claim("两者均包含前向碰撞探测/监测、自动制动减速以及避免或减轻碰撞目的。", "gb39901:clause:3.1", "unece_r152:clause:2.1"), claim("GB定义显式包含警告信号和实时监测；UNECE定义强调自动探测与激活制动。", "gb39901:clause:3.1", "unece_r152:clause:2.1")],
        "evidence": ["gb39901:clause:3.1", "unece_r152:clause:2.1"],
        "steps": [("Definition", "GB AEBS定义", "gb39901:clause:3.1"), ("SemanticAlignment", "探测、制动、避免或减轻", ["gb39901:clause:3.1", "unece_r152:clause:2.1"]), ("Definition", "UNECE AEBS定义", "unece_r152:clause:2.1"), ("Difference", "GB显式警告与实时监测", ["gb39901:clause:3.1", "unece_r152:clause:2.1"])],
        "reason": "需做定义级语义对齐而不是字符串相似，区分共同核心与一方额外表述。",
        "scoring": "claim_f1",
    },
    {
        "id": "cross_compare_003", "task_type": "cross_document_comparison",
        "question": "GB 39901、UNECE R152与Euro NCAP C2C日光试验的最低光照要求如何比较？",
        "answer": {"GB39901": {"6.5_to_6.7_car_tests": ">=1000 lx", "other_tests": ">=2000 lx"}, "UNECE_R152": {"car_to_car": ">1000 lux", "car_to_pedestrian_and_bicycle": ">2000 lux"}, "Euro_NCAP_C2C": {"daylight_tests": ">2000 lux"}},
        "claims": [claim("GB车辆目标试验不小于1000 lx，其他试验不小于2000 lx。", "gb39901:clause:6.4"), claim("UNECE车对车超过1000 lux，行人和自行车超过2000 lux。", "unece_r152:clause:6.1.5"), claim("Euro NCAP C2C日光试验统一要求超过2000 lux。", "euroncap_c2c:clause:7.2.3")],
        "evidence": ["gb39901:clause:6.4", "unece_r152:clause:6.1.5", "euroncap_c2c:clause:7.2.3"],
        "steps": [("EnvironmentRequirement", "GB光照阈值", "gb39901:clause:6.4"), ("Comparison", "法规按目标类型分档", ["gb39901:clause:6.4", "unece_r152:clause:6.1.5"]), ("EnvironmentRequirement", "UNECE光照阈值", "unece_r152:clause:6.1.5"), ("ProtocolRequirement", "Euro NCAP日光>2000 lux", "euroncap_c2c:clause:7.2.3")],
        "reason": "三个文档的阈值、比较符和适用试验集合不同，需要条件化比较。",
        "scoring": "claim_f1",
    },
    {
        "id": "cross_synthesis_001", "task_type": "cross_document_synthesis",
        "question": "比较GB 39901与UNECE R152对误响应的验证证据：各自如何规定场景与可接受的证据形式？",
        "answer": {"GB39901": "5.4给出不预警且不制动的判据，6.11规定五项具体场地试验", "UNECE_R152": "附录3附录2给出场景，制造商解释安全策略并提供仿真、真实道路或场地试验等行为证据；技术服务认为需要时按参数演示", "difference": "GB把五项场景写成明确试验方法，UNECE明确允许多种证据形式"},
        "claims": [claim("GB以5.4判据和6.11五项具体试验验证误响应。", "gb39901:clause:5.4", "gb39901:clause:6.11"), claim("UNECE要求解释策略，并允许仿真、真实道路或场地数据作为场景行为证据。", "unece_r152:annex3:appendix2"), claim("两者都关注无碰撞风险下避免误反应，但证据制度不同。", "gb39901:clause:5.4", "unece_r152:annex3:appendix2")],
        "evidence": ["gb39901:clause:5.4", "gb39901:clause:6.11", "unece_r152:annex3:appendix2"],
        "steps": [("Requirement", "GB误响应判据", "gb39901:clause:5.4"), ("TestSuite", "GB 6.11五项试验", "gb39901:clause:6.11"), ("EvidencePolicy", "UNECE多形式行为证据", "unece_r152:annex3:appendix2"), ("Comparison", "共同目的与证据形式差异", ["gb39901:clause:5.4", "unece_r152:annex3:appendix2"])],
        "reason": "综合法规要求、测试协议和证据政策，需跨三段恢复‘要求—场景—证据形式’链。",
        "scoring": "claim_f1",
    },
    {
        "id": "cross_synthesis_002", "task_type": "cross_document_synthesis",
        "question": "以M1车辆60 km/h驶向静止车辆目标、最大设计总质量为例，说明GB法规阈值、Euro NCAP场景执行和评分指标如何组成三层评估链。",
        "answer": {"GB_regulatory_layer": "表1给出最大相对碰撞速度35 km/h", "Euro_NCAP_test_layer": "语义映射为CCRs，使用符合ISO 19206-3:2021要求的GVT系统执行协议场景", "Euro_NCAP_scoring_layer": "CCRs以Vimpact为评估指标且须先满足评分资格条件", "interpretation": "法规合规结果不能直接换算为Euro NCAP分数"},
        "claims": [claim("GB表1在M1、60 km/h、静止目标、最大设计总质量下阈值为35 km/h。", "gb39901:table:1:row:60"), claim("该场景语义对应Euro NCAP CCRs，并由GVT协议执行。", "euroncap_c2c:clause:2.2", "euroncap_c2c:clause:5.1"), claim("Euro NCAP对CCRs使用Vimpact评分且另有资格前提，因此GB合规不等于确定分数。", "euroncap_score:clause:3.3")],
        "evidence": ["gb39901:table:1:row:60", "euroncap_c2c:clause:2.2", "euroncap_c2c:clause:5.1", "euroncap_score:clause:3.3"],
        "steps": [("RegulatoryThreshold", "GB M1静止目标60 km/h总质量阈值35 km/h", "gb39901:table:1:row:60"), ("ScenarioMapping", "Euro NCAP CCRs", "euroncap_c2c:clause:2.2"), ("TestProtocol", "GVT与ISO 19206-3:2021", "euroncap_c2c:clause:5.1"), ("ScoringMetric", "CCRs使用Vimpact并受资格条件约束", "euroncap_score:clause:3.3")],
        "reason": "需要跨法规阈值、测试协议和评分协议建立三层链，任何单一文档都不足以回答。",
        "scoring": "claim_f1",
    },
    {
        "id": "cross_unanswerable_001", "task_type": "cross_document_unanswerable", "answerable": False,
        "question": "某M1车型只要通过GB 39901中60 km/h静止车辆目标、最大设计总质量试验，就必然能在Euro NCAP AEB Car-to-Car中获得多少精确分数？",
        "answer": {"answerable": False, "reason": "无法推出精确分数。GB只给该法规工况的合规阈值；Euro NCAP还要求评分资格，并基于多个CCRs/CCRm/CCRb点及Vimpact、Vrel_impact等指标归一化评分。"},
        "claims": [],
        "evidence": ["gb39901:table:1:row:60", "euroncap_score:clause:3.3"],
        "steps": [("ComplianceResult", "GB单一静止目标工况", "gb39901:table:1:row:60"), ("ScoringFramework", "Euro NCAP资格与多指标评分", "euroncap_score:clause:3.3"), ("MissingEvidence", "缺少完整测试网格与资格信息", "euroncap_score:clause:3.3")],
        "reason": "故意混淆法规合规与消费评分；证据明确显示评分需要额外资格和多场景数据。",
    },
]


REVIEW_CHECKLIST = {
    "source_context_read": True,
    "answer_rederived": True,
    "conditions_complete": True,
    "counterexample_checked": True,
    "single_chunk_sufficiency_checked": True,
    "mechanical_validation_passed": True,
}


def relation_for(target_type: str) -> str:
    return {
        "Clause": "CONTAINS",
        "Definition": "DEFINES",
        "VehicleCategorySet": "APPLIES_TO",
        "Date": "HAS_EFFECTIVE_DATE",
        "Requirement": "SPECIFIES",
        "RequirementSet": "SPECIFIES",
        "TestScenario": "VERIFIED_BY",
        "Condition": "HAS_CONDITION",
        "LoadState": "HAS_LOAD_STATE",
        "Threshold": "HAS_THRESHOLD",
        "Signal": "REQUIRES_SIGNAL",
    }.get(target_type, "RELATED_TO")


def materialize_questions(limit: int | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    selected = QUESTION_SPECS[:limit] if limit else QUESTION_SPECS
    graph: list[dict[str, Any]] = []
    questions: list[dict[str, Any]] = []
    for ordinal, spec in enumerate(selected, 1):
        node_ids: list[str] = []
        edge_ids: list[str] = []
        primary_evidence = spec["evidence"][0]
        previous_step_evidence: list[str] = []
        for index, step in enumerate(spec["steps"], 1):
            node_type, name = step[:2]
            raw_step_evidence = step[2] if len(step) == 3 else primary_evidence
            step_evidence = [raw_step_evidence] if isinstance(raw_step_evidence, str) else list(raw_step_evidence)
            node_id = f"n:{spec['id']}:{index:02d}"
            node_ids.append(node_id)
            graph.append({"kind": "node", "id": node_id, "type": node_type, "name": name, "aliases": [], "properties": {}, "evidence_ids": step_evidence})
            if index > 1:
                edge_id = f"e:{spec['id']}:{index - 1:02d}"
                edge_ids.append(edge_id)
                edge_evidence = list(dict.fromkeys(previous_step_evidence + step_evidence))
                graph.append({"kind": "edge", "id": edge_id, "source": node_ids[-2], "target": node_id, "relation": relation_for(node_type), "properties": {}, "evidence_ids": edge_evidence})
            previous_step_evidence = step_evidence
        atomic_claims = []
        for claim_index, item in enumerate(spec["claims"], 1):
            atomic_claims.append({"id": f"{spec['id']}:claim:{claim_index:02d}", **item})
        answerable = spec.get("answerable", True)
        method = spec.get("scoring", "structured_exact_match" if answerable else "unanswerable")
        questions.append(
            {
                "id": spec["id"],
                "question": spec["question"],
                "task_type": spec["task_type"],
                "answerable": answerable,
                "gold_answer": spec["answer"],
                "atomic_claims": atomic_claims,
                "gold_evidence_ids": spec["evidence"],
                "gold_nodes": node_ids,
                "gold_edges": edge_ids,
                "gold_path": edge_ids,
                "expected_hops": len(edge_ids),
                "graph_dependency_reason": spec["reason"],
                "scoring_method": method,
                "review_status": "self_checked",
                "split": "dev" if ordinal <= 12 else "test",
                "self_review": dict(REVIEW_CHECKLIST),
            }
        )
    return graph, questions


def audit_gold(question_count: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return a separate, schema-valid extraction gold graph and its ten units."""
    if question_count < 50:
        return [], []
    graph: list[dict[str, Any]] = []
    units: list[dict[str, Any]] = []

    def add_unit(
        unit_id: str,
        kind: str,
        title: str,
        evidence_id: str,
        nodes: list[tuple[str, str, str, list[str]]],
        edges: list[tuple[str, str, str, str]],
        tuples: list[dict[str, Any]],
        aliases: dict[str, list[str]],
    ) -> None:
        node_ids = []
        edge_ids = []
        for suffix, node_type, name, node_aliases in nodes:
            node_id = f"n:{unit_id}:{suffix}"
            node_ids.append(node_id)
            record = {"kind": "node", "id": node_id, "type": node_type, "name": name,
                      "aliases": node_aliases, "properties": {"audit_unit": unit_id}, "evidence_ids": [evidence_id]}
            if suffix == "threshold" and tuples:
                record["numeric_condition_tuples"] = tuples
            graph.append(record)
        for index, (source_suffix, relation, target_suffix, description) in enumerate(edges, 1):
            edge_id = f"e:{unit_id}:{index:02d}"
            edge_ids.append(edge_id)
            graph.append(
                {"kind": "edge", "id": edge_id, "source": f"n:{unit_id}:{source_suffix}",
                 "target": f"n:{unit_id}:{target_suffix}", "relation": relation,
                 "properties": {"audit_unit": unit_id, "description": description}, "evidence_ids": [evidence_id]}
            )
        units.append(
            {"id": unit_id, "kind": kind, "title": title, "evidence_id": evidence_id,
             "selection_reason": "代表性叙述关系完整标注" if kind == "narrative" else "代表性表格行的实体、关系、数值与条件完整标注",
             "gold_nodes": node_ids, "gold_edges": edge_ids,
             "gold_numeric_condition_tuples": tuples, "gold_aliases": aliases,
             "review_status": "self_checked"}
        )

    add_unit(
        "audit_narrative_001", "narrative", "AEBS定义", "gb39901:clause:3.1",
        [("clause", "Clause", "GB 39901-2025第3.1条", []),
         ("system", "System", "自动紧急制动系统", ["AEBS", "AEB系统"]),
         ("monitor", "SystemFunction", "实时监测车辆前方行驶环境", []),
         ("warning", "SystemFunction", "碰撞预警", []),
         ("braking", "SystemFunction", "紧急制动", [])],
        [("clause", "DEFINES", "system", "条款定义AEBS"),
         ("system", "HAS_FUNCTION", "monitor", "AEBS实时监测"),
         ("system", "HAS_FUNCTION", "warning", "AEBS发出碰撞警告"),
         ("system", "HAS_FUNCTION", "braking", "AEBS自动制动减速")],
        [], {"自动紧急制动系统": ["AEBS", "AEB系统"]},
    )
    add_unit(
        "audit_narrative_002", "narrative", "车辆目标预警时机", "gb39901:clause:5.1.1",
        [("clause", "Clause", "GB 39901-2025第5.1.1条", []),
         ("requirement", "Requirement", "[5.1.1]车辆目标碰撞预警时序要求", []),
         ("test", "TestScenario", "[6.5-6.7]车辆目标碰撞预警和紧急制动试验", []),
         ("metric", "Metric", "碰撞预警提前时间", []),
         ("threshold", "Threshold", "[5.1.1]碰撞预警提前时间≥0.8s阈值", [])],
        [("clause", "SPECIFIES", "requirement", "条款给出预警要求"),
         ("requirement", "VERIFIED_BY", "test", "要求由6.5至6.7验证"),
         ("requirement", "MEASURED_BY", "metric", "要求以预警提前时间度量"),
         ("metric", "HAS_THRESHOLD", "threshold", "提前时间阈值为0.8s")],
        [{"value": 0.8, "unit": "s", "operator": ">=", "condition": "车辆目标碰撞预警相对紧急制动提前时间"}], {},
    )
    add_unit(
        "audit_narrative_003", "narrative", "无误响应要求", "gb39901:clause:5.4",
        [("clause", "Clause", "GB 39901-2025第5.4条", []),
         ("requirement", "Requirement", "[5.4]无碰撞危险时不应发出预警和制动要求", ["系统无误响应要求"]),
         ("condition", "Condition", "不存在碰撞危险", []),
         ("test", "TestScenario", "[6.11]系统误响应试验", []),
         ("acceptance", "AcceptanceCriterion", "不发出碰撞预警和紧急制动", [])],
        [("clause", "SPECIFIES", "requirement", "条款规定无误响应"),
         ("requirement", "HAS_CONDITION", "condition", "适用于无碰撞危险"),
         ("requirement", "VERIFIED_BY", "test", "由6.11验证"),
         ("requirement", "HAS_ACCEPTANCE_CRITERION", "acceptance", "共同合格行为")],
        [], {"无碰撞危险时不应发出预警和制动要求": ["系统无误响应要求"]},
    )
    add_unit(
        "audit_narrative_004", "narrative", "非预期侧向运动安全链", "gb39901:appendix:A.2.3",
        [("clause", "Clause", "GB 39901-2025第A.2.3.1条", []),
         ("hazard", "Hazard", "非预期的侧向运动", []),
         ("asil", "ASILLevel", "ASIL D", ["汽车安全完整性等级D"]),
         ("goal", "SafetyGoal", "避免非预期侧向运动导致车辆失稳", []),
         ("accel", "Metric", "侧向加速度变化值或最大值", []),
         ("displacement", "Metric", "侧向位移", []),
         ("yaw", "Metric", "横摆角速度变化值", [])],
        [("clause", "SPECIFIES", "hazard", "表A.1列出危害"),
         ("hazard", "ASSIGNED_ASIL", "asil", "危害分配ASIL D"),
         ("hazard", "HAS_SAFETY_GOAL", "goal", "危害关联安全目标"),
         ("hazard", "MEASURED_BY", "accel", "侧向加速度安全度量"),
         ("hazard", "MEASURED_BY", "displacement", "侧向位移安全度量"),
         ("hazard", "MEASURED_BY", "yaw", "横摆角速度安全度量")],
        [], {"ASIL D": ["汽车安全完整性等级D"]},
    )
    add_unit(
        "audit_narrative_005", "narrative", "仿真替代与场地复核", "gb39901:clause:6.14",
        [("clause", "Clause", "GB 39901-2025第6.14条", []),
         ("simulation", "TestScenario", "6.5至6.10仿真试验", []),
         ("toolchain", "SimulationToolchain", "仿真试验工具链", ["仿真工具链"]),
         ("verification", "VerificationActivity", "仿真试验工具链验证和确认", []),
         ("field", "AcceptanceCriterion", "同一速度和载荷至少一次场地试验", []),
         ("third", "AcceptanceCriterion", "结果不一致时第3次为场地试验", [])],
        [("clause", "SPECIFIES", "simulation", "6.14规定仿真试验"),
         ("simulation", "USES_TOOLCHAIN", "toolchain", "仿真试验使用工具链"),
         ("verification", "VALIDATES", "toolchain", "工具链须验证确认"),
         ("simulation", "HAS_ACCEPTANCE_CRITERION", "field", "至少一次场地试验"),
         ("simulation", "HAS_ACCEPTANCE_CRITERION", "third", "冲突时第三次场地试验")],
        [], {"仿真试验工具链": ["仿真工具链"]},
    )

    def add_table_unit(
        unit_id: str, title: str, evidence_id: str, clause: str, vehicle: str,
        scenario: str, ego: int, target: int, value: int, table: str, aliases: dict[str, list[str]],
    ) -> None:
        qualifier = f"{vehicle}，最大设计总质量，试验车{ego}km/h，目标{target}km/h"
        add_unit(
            unit_id, "table", title, evidence_id,
            [("clause", "Clause", f"GB 39901-2025第{clause}条", []),
             ("vehicle", "VehicleCategory", f"{vehicle}类汽车", [vehicle]),
             ("requirement", "Requirement", f"[{clause}] {vehicle}类{scenario}最大相对碰撞速度要求", []),
             ("scenario", "TestScenario", scenario, []),
             ("load", "LoadState", "最大设计总质量", ["最大总质量"]),
             ("condition", "Condition", f"试验车{ego} km/h且目标{target} km/h", []),
             ("metric", "Metric", "最大相对碰撞速度", []),
             ("threshold", "Threshold", f"[{clause}]最大相对碰撞速度≤{value} km/h({qualifier})", [])],
            [("clause", "SPECIFIES", "requirement", f"表{table}所属条款"),
             ("requirement", "APPLIES_TO", "vehicle", "车型限定"),
             ("requirement", "VERIFIED_BY", "scenario", "场景限定"),
             ("requirement", "HAS_LOAD_STATE", "load", "载荷限定"),
             ("requirement", "HAS_CONDITION", "condition", "速度组合条件"),
             ("requirement", "MEASURED_BY", "metric", "评价指标"),
             ("requirement", "HAS_THRESHOLD", "threshold", "数值阈值"),
             ("metric", "HAS_THRESHOLD", "threshold", "指标阈值"),
             ("threshold", "APPLIES_TO", "load", "阈值载荷限定")],
            [{"value": value, "unit": "km/h", "operator": "<=", "condition": f"{vehicle};{scenario};试验车{ego} km/h;目标{target} km/h;最大设计总质量"}],
            {"最大设计总质量": ["最大总质量"], **aliases},
        )

    add_table_unit("audit_table_001", "表1 M1静止目标60 km/h行", "gb39901:table:1:row:60", "5.2.1.1", "M1", "静止车辆目标场景", 60, 0, 35, "1", {})
    add_table_unit("audit_table_002", "表4 N1匀速目标60/20 km/h行", "gb39901:table:4:row:60", "5.2.1.2", "N1", "匀速车辆目标场景", 60, 20, 10, "4", {})
    add_table_unit("audit_table_003", "表8 N1儿童目标40/5 km/h行", "gb39901:table:8:row:40", "5.2.2", "N1", "儿童行人目标横穿场景", 40, 5, 10, "8", {"儿童行人目标": ["儿童目标"]})
    add_table_unit("audit_table_004", "表10 N1自行车目标60/15 km/h行", "gb39901:table:10:row:60", "5.2.3", "N1", "自行车目标横穿场景", 60, 15, 45, "10", {"自行车目标": ["自行车骑行者目标"]})
    add_table_unit("audit_table_005", "表12 N1摩托车目标40/20 km/h行", "gb39901:table:12:row:40", "5.2.4", "N1", "踏板式两轮摩托车目标横穿场景", 40, 20, 25, "12", {"踏板式两轮摩托车目标": ["PTW目标", "动力两轮车目标"]})
    return graph, units


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="materialize the first N curated questions")
    args = parser.parse_args()
    if args.limit is not None and not 1 <= args.limit <= len(QUESTION_SPECS):
        raise SystemExit(f"--limit must be between 1 and {len(QUESTION_SPECS)}")
    graph, questions = materialize_questions(args.limit)
    audit_graph, audits = audit_gold(len(questions))
    graph.extend(audit_graph)
    write_jsonl(EVIDENCE_PATH, evidence_records())
    write_jsonl(GRAPH_PATH, graph)
    write_jsonl(QUESTIONS_PATH, questions)
    write_jsonl(AUDIT_PATH, audits)
    print(f"curated evidence={len(EVIDENCE_SPECS)} graph_records={len(graph)} questions={len(questions)}")
    print(f"task_counts={dict(Counter(item['task_type'] for item in questions))}")


if __name__ == "__main__":
    main()
