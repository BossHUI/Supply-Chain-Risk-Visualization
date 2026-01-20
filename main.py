#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
简化版风险报告解析脚本
专注于解析 research_assessment_manager_report.md 格式的报告
"""

import os
import re
import json
import math
from typing import List, Dict, Optional, Tuple


class RiskReportParser:
    """风险报告解析器"""
    
    def __init__(self, file_path: str):
        """
        初始化解析器
        
        参数:
            file_path: 报告文件路径
        """
        self.file_path = file_path
        self.content = self._load_file()
    
    def _load_file(self) -> str:
        """加载报告文件"""
        if not os.path.exists(self.file_path):
            raise FileNotFoundError(f"未找到报告文件: {self.file_path}")
        
        with open(self.file_path, 'r', encoding='utf-8') as f:
            return f.read()
    
    def extract_title(self) -> Optional[str]:
        """提取报告标题"""
        # 匹配：## 标题：xxx
        pattern = r'##\s*标题[：:]\s*(.+)'
        match = re.search(pattern, self.content)
        if match:
            return match.group(1).strip()
        
        # 匹配：### xxx（三级标题，如"### 安世供应链外部风险评估报告"）
        pattern = r'^###\s+(.+?)(?:\n|$)'
        match = re.search(pattern, self.content, re.MULTILINE)
        if match:
            title = match.group(1).strip()
            # 排除"作者署名"等非标题内容
            if '作者署名' not in title and '风险' in title:
                return title
        
        # 如果没有找到，尝试从一级标题提取
        pattern = r'^#\s+(.+)$'
        match = re.search(pattern, self.content, re.MULTILINE)
        if match:
            return match.group(1).strip()
        
        return None
    
    def normalize_location(self, location: str) -> Optional[str]:
        """
        规范化地理位置名称
        - 合并缩写（如"印尼" -> "印度尼西亚"）
        - 返回None表示应该过滤掉的模糊地区
        
        参数:
            location: 原始地理位置名称
        
        返回:
            str: 规范化后的地理位置名称，或None（如果应该过滤）
        """
        # 模糊地区列表（应该过滤掉）
        vague_locations = {
            '中部', '沿海地区', '国内', '海外', '东南亚',  # 太模糊
            '广汽', '本田', '安世'  # 公司名称，不是地理位置
        }
        
        if location in vague_locations:
            return None
        
        # 缩写映射（统一使用完整名称）
        abbreviation_map = {
            '印尼': '印度尼西亚',
            '欧盟': '欧洲',  # 欧盟统一为欧洲
        }
        
        # 如果找到缩写，返回完整名称
        if location in abbreviation_map:
            return abbreviation_map[location]
        
        return location
    
    def extract_location_relationships(self) -> Dict[str, str]:
        """
        从报告文本中动态提取地理位置之间的关系
        
        返回:
            Dict[str, str]: 子地区 -> 父地区的映射字典
        """
        relationships = {}
        
        # 关系模式：匹配"子地区 关系词 父地区"的模式
        # 例如："塞梅鲁火山位于东爪哇省"、"塞梅鲁属于东爪哇"等
        relationship_patterns = [
            # 模式1: "塞梅鲁火山位于东爪哇省"
            r'([^\s，,。；;、]+?)(?:火山|山|地区|市|省|县|区|镇|村)?(?:位于|属于|在|处于|地处|坐落于)([^\s，,。；;、]+?)(?:省|市|县|区|地区|州)',
            # 模式2: "塞梅鲁位于东爪哇"
            r'([^\s，,。；;、]+?)(?:位于|属于|在|处于|地处|坐落于)([^\s，,。；;、]+?)(?:省|市|县|区|地区|州)?',
            # 模式3: "塞梅鲁的东爪哇省"
            r'([^\s，,。；;、]+?)(?:的|地)([^\s，,。；;、]+?)(?:省|市|县|区|地区|州)',
            # 模式4: "东爪哇省的塞梅鲁火山"（需要反转）
            r'([^\s，,。；;、]+?)(?:省|市|县|区|地区|州)(?:的|地)([^\s，,。；;、]+?)(?:火山|山|地区|市|省|县|区|镇|村)?',
        ]
        
        # 从整个报告内容中提取关系
        content = self.content
        
        # 尝试匹配各种关系模式
        for pattern_idx, pattern in enumerate(relationship_patterns):
            matches = re.finditer(pattern, content, re.IGNORECASE)
            for match in matches:
                if pattern_idx == 3:
                    # 模式4需要反转：父地区在前，子地区在后
                    parent = match.group(1).strip()
                    child = match.group(2).strip()
                else:
                    child = match.group(1).strip()
                    parent = match.group(2).strip()
                
                # 清理提取的文本（移除常见后缀）
                child = re.sub(r'(?:火山|山|地区|市|省|县|区|镇|村)$', '', child).strip()
                parent = re.sub(r'(?:火山|山|地区|市|省|县|区|镇|村)$', '', parent).strip()
                
                # 规范化地理位置名称
                child_normalized = self.normalize_location(child)
                parent_normalized = self.normalize_location(parent)
                
                # 如果两个都是有效的地理位置，且不相同
                if (child_normalized and parent_normalized and 
                    child_normalized != parent_normalized and
                    child_normalized not in ['未明确'] and
                    parent_normalized not in ['未明确']):
                    # 避免循环关系
                    if parent_normalized not in relationships or relationships[parent_normalized] != child_normalized:
                        relationships[child_normalized] = parent_normalized
        
        # 基于坐标距离推断关系（如果两个地点非常接近，可能是同一地区）
        # 只检查报告中实际出现的地理位置
        # 从报告中提取所有地理位置
        all_report_locations = set()
        location_keywords = [
            '荷兰', '中国', '日本', '美国', '欧盟', '欧洲', '德国', '法国', '英国',
            '澳大利亚', '韩国', '印度', '越南', '印尼', '印度尼西亚',
            '福岛', '莱茵河', '鹿儿岛', '塞梅鲁', '东爪哇', '东莞',
        ]
        
        for keyword in location_keywords:
            if keyword in content:
                normalized = self.normalize_location(keyword)
                if normalized and normalized not in ['未明确']:
                    all_report_locations.add(normalized)
        
        # 获取所有已知的地理位置坐标
        location_coords = self._get_all_location_coords()
        
        # 只计算报告中出现的地理位置之间的距离
        report_locations_list = list(all_report_locations)
        for i, loc1 in enumerate(report_locations_list):
            for loc2 in report_locations_list[i+1:]:
                if loc1 == loc2:
                    continue
                
                # 如果已经存在关系，跳过
                if loc1 in relationships or loc2 in relationships:
                    continue
                
                # 获取坐标
                coord1 = location_coords.get(loc1)
                coord2 = location_coords.get(loc2)
                
                if not coord1 or not coord2:
                    continue
                
                # 计算两个地点之间的距离（使用Haversine公式）
                distance = self._calculate_distance(coord1, coord2)
                
                # 如果距离小于100公里，可能是同一地区
                # 选择名称更具体的作为父地区（通常名称更长的更具体，或者包含"省"、"市"等后缀的）
                if distance < 100:  # 100公里阈值
                    # 判断哪个更具体（名称更长，或包含行政级别后缀）
                    loc1_is_more_specific = (
                        len(loc1) > len(loc2) or 
                        any(suffix in loc1 for suffix in ['省', '市', '县', '区', '州'])
                    )
                    loc2_is_more_specific = (
                        len(loc2) > len(loc1) or 
                        any(suffix in loc2 for suffix in ['省', '市', '县', '区', '州'])
                    )
                    
                    if loc2_is_more_specific and not loc1_is_more_specific:
                        relationships[loc1] = loc2
                    elif loc1_is_more_specific and not loc2_is_more_specific:
                        relationships[loc2] = loc1
        
        return relationships
    
    def _get_all_location_coords(self) -> Dict[str, Tuple[float, float]]:
        """获取所有已知地理位置的坐标"""
        return {
            '荷兰': (52.1326, 5.2913),
            '中国': (35.8617, 104.1954),
            '日本': (36.2048, 138.2529),
            '美国': (37.0902, -95.7129),
            '欧盟': (50.1109, 8.6821),
            '欧洲': (50.1109, 8.6821),
            '德国': (51.1657, 10.4515),
            '法国': (46.2276, 2.2137),
            '英国': (55.3781, -3.4360),
            '澳大利亚': (-25.2744, 133.7751),
            '韩国': (35.9078, 127.7669),
            '印度': (20.5937, 78.9629),
            '越南': (14.0583, 108.2772),
            '印度尼西亚': (-0.7893, 113.9213),
            '鹿儿岛': (31.5966, 130.5571),
            '塞梅鲁': (-8.1080, 112.9225),
            '东爪哇': (-7.5361, 112.2384),
            '东莞': (23.0207, 113.7518),
            '福岛': (37.75, 140.47),
            '莱茵河': (50.0, 7.0),
        }
    
    def _calculate_distance(self, coord1: Tuple[float, float], coord2: Tuple[float, float]) -> float:
        """
        计算两个地理坐标之间的距离（公里）
        使用Haversine公式
        """
        lat1, lon1 = coord1
        lat2, lon2 = coord2
        
        # 转换为弧度
        lat1_rad = math.radians(lat1)
        lon1_rad = math.radians(lon1)
        lat2_rad = math.radians(lat2)
        lon2_rad = math.radians(lon2)
        
        # Haversine公式
        dlat = lat2_rad - lat1_rad
        dlon = lon2_rad - lon1_rad
        
        a = math.sin(dlat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon/2)**2
        c = 2 * math.asin(math.sqrt(a))
        
        # 地球半径（公里）
        R = 6371.0
        
        return R * c
    
    def filter_redundant_locations(self, locations: List[str]) -> List[str]:
        """
        过滤冗余的地理位置
        当同时存在更具体的地点（如"东爪哇"）和更宽泛的地点（如"印度尼西亚"）时，
        只保留更具体的地点
        
        参数:
            locations: 地理位置列表
        
        返回:
            List[str]: 过滤后的地理位置列表
        """
        if not locations:
            return locations
        
        # 定义地理位置层级关系（具体地点 -> 所属国家/地区）
        # 这些是基础的国家-地区关系，通常不会变化
        location_hierarchy = {
            # 印尼的具体地区
            '东爪哇': '印度尼西亚',
            '塞梅鲁': '印度尼西亚',  # 塞梅鲁火山在印尼
            # 日本的具体地区
            '鹿儿岛': '日本',
            '福岛': '日本',
            # 中国的具体地区
            '东莞': '中国',
            # 其他具体地区
            '莱茵河': '德国',  # 莱茵河主要在德国
        }
        
        # 手动配置的地区到地区的映射（子地区 -> 父地区）
        # 这些是已知的固定关系，作为补充
        manual_region_to_region = {
            '塞梅鲁': '东爪哇',  # 塞梅鲁火山属于东爪哇省
        }
        
        # 动态提取地区到地区的映射（从报告文本中提取）
        # 优先使用动态提取的关系，因为它更符合当前报告的内容
        dynamic_region_to_region = self.extract_location_relationships()
        
        # 合并关系映射：动态提取的关系优先，手动配置作为补充
        region_to_region = {**manual_region_to_region, **dynamic_region_to_region}
        
        # 创建反向映射：国家 -> 该国家的所有具体地区
        country_to_regions = {}
        for region, country in location_hierarchy.items():
            if country not in country_to_regions:
                country_to_regions[country] = []
            country_to_regions[country].append(region)
        
        filtered = []
        for loc in locations:
            # 如果这个地点是某个地区的子地区（如塞梅鲁 -> 东爪哇），检查父地区是否也在列表中
            if loc in region_to_region:
                parent_region = region_to_region[loc]
                # 如果列表中同时有子地区和父地区，跳过子地区，只保留父地区
                if parent_region in locations:
                    continue  # 跳过子地区
                else:
                    # 如果没有父地区，添加子地区
                    if loc not in filtered:
                        filtered.append(loc)
            # 如果这个地点是某个国家的具体地区
            elif loc in location_hierarchy:
                country = location_hierarchy[loc]
                # 如果列表中同时有这个具体地区和所属国家，跳过国家
                if country in locations:
                    # 只添加具体地区，不添加国家
                    if loc not in filtered:
                        filtered.append(loc)
                else:
                    # 如果没有国家，添加具体地区
                    if loc not in filtered:
                        filtered.append(loc)
            else:
                # 如果这个地点是国家，检查是否有更具体的地区
                has_specific_region = False
                if loc in country_to_regions:
                    for region in country_to_regions[loc]:
                        if region in locations:
                            has_specific_region = True
                            break
                
                # 如果有更具体的地区，跳过这个国家
                if not has_specific_region:
                    if loc not in filtered:
                        filtered.append(loc)
        
        return filtered if filtered else locations
    
    def extract_location_from_text(self, text: str) -> List[str]:
        """
        从文本中提取地理位置信息
        
        参数:
            text: 要分析的文本
        
        返回:
            List[str]: 地理位置列表（已规范化）
        """
        locations = []
        
        # 常见地理位置关键词（包含所有可能的变体）
        location_keywords = [
            '荷兰', '中国', '日本', '美国', '欧盟', '欧洲', '德国', '法国', '英国',
            '澳大利亚', '韩国', '印度', '越南', '印尼', '印度尼西亚',
            '福岛', '莱茵河', '鹿儿岛', '塞梅鲁', '东爪哇', '东莞',
            # 模糊地区（用于匹配，但会被过滤）
            '中部', '沿海地区', '国内', '海外', '东南亚',
            '广汽', '本田', '安世'
        ]
        
        # 从文本中查找地理位置
        for keyword in location_keywords:
            if keyword in text:
                # 规范化地理位置
                normalized = self.normalize_location(keyword)
                if normalized and normalized not in locations:
                    locations.append(normalized)
        
        # 如果没有找到明确位置，尝试从风险速览中提取
        if not locations:
            summary = self.extract_risk_summary()
            if summary:
                for keyword in location_keywords:
                    if keyword in summary:
                        normalized = self.normalize_location(keyword)
                        if normalized and normalized not in locations:
                            locations.append(normalized)
        
        # 过滤冗余的地理位置（如果同时有具体地区和所属国家，只保留具体地区）
        locations = self.filter_redundant_locations(locations)
        
        return locations if locations else ['未明确']
    
    def extract_risk_list(self) -> List[Dict]:
        """
        提取风险清单表格
        
        返回:
            List[Dict]: 风险列表，每个风险包含序号、名称、类别、等级、描述、地理位置
        """
        risks = []
        
        # 匹配表格行：| 序号 | 风险名称 | 风险类别 | 风险等级 | 风险描述 |
        # 跳过表头行
        pattern = r'\|\s*(\d+)\s*\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|'
        matches = re.findall(pattern, self.content)
        
        for match in matches:
            seq, name, category, level, description = match
            # 提取地理位置（extract_location_from_text已经应用了规范化和去重）
            locations = self.extract_location_from_text(description)
            # 也从风险详情中提取
            risk_details = self.extract_risk_details()
            for detail in risk_details:
                if detail['序号'] == int(seq.strip()):
                    trigger_text = detail.get('触发条件', '') or ''
                    if trigger_text:
                        detail_locations = self.extract_location_from_text(trigger_text)
                        for loc in detail_locations:
                            if loc not in locations and loc != '未明确':
                                locations.append(loc)
                    break
            
            # 再次过滤冗余（因为可能从多个来源提取，需要统一去重）
            locations = self.filter_redundant_locations(locations)
            
            risks.append({
                '序号': int(seq.strip()),
                '风险名称': name.strip(),
                '风险类别': category.strip(),
                '风险等级': level.strip(),
                '风险描述': description.strip(),
                '地理位置': locations  # 已经规范化过了
            })
        
        return risks
    
    def extract_risk_details(self) -> List[Dict]:
        """
        提取风险详情
        
        返回:
            List[Dict]: 风险详情列表，每个风险包含触发条件、风险表现、风险等级、判断依据、风险应对
        """
        details = []
        
        # 匹配风险详情块：##### （序号）风险名称
        # 然后提取后续内容直到下一个风险或章节结束
        pattern = r'#####\s*（(\d+)）\s*([^\n]+)\n(.*?)(?=#####|####|###|$)'
        matches = re.findall(pattern, self.content, re.DOTALL)
        
        for seq, name, content in matches:
            detail = {
                '序号': int(seq),
                '风险名称': name.strip(),
                '触发条件': self._extract_field(content, '触发条件'),
                '风险表现': self._extract_field(content, '风险表现'),
                '风险等级': self._extract_field(content, '风险等级'),
                '判断依据': self._extract_judgment_basis(content),
                '风险应对': self._extract_countermeasures(content)
            }
            details.append(detail)
        
        return details
    
    def _extract_field(self, content: str, field_name: str) -> Optional[str]:
        """提取字段内容"""
        pattern = rf'- \*\*{field_name}[：:]\*\*\s*(.+?)(?=\n-|\n#####|$)'
        match = re.search(pattern, content, re.DOTALL)
        if match:
            return match.group(1).strip()
        return None
    
    def _extract_judgment_basis(self, content: str) -> Optional[str]:
        """提取判断依据"""
        # 判断依据可能在风险等级字段下
        pattern = r'- \*\*风险等级[：:]\*\*\s*([^\n]+)\s*\n\s*- 判断依据[：:]\s*(.+?)(?=\n-|\n#####|$)'
        match = re.search(pattern, content, re.DOTALL)
        if match:
            return match.group(2).strip()
        return None
    
    def _extract_countermeasures(self, content: str) -> List[str]:
        """提取风险应对措施"""
        countermeasures = []
        
        # 匹配风险应对部分
        pattern = r'- \*\*风险应对[：:]\*\*\s*(.*?)(?=\n-|\n#####|$)'
        match = re.search(pattern, content, re.DOTALL)
        if match:
            measures_text = match.group(1)
            # 提取编号列表项
            pattern_items = r'\d+\.\s*([^\n]+)'
            items = re.findall(pattern_items, measures_text)
            countermeasures = [item.strip() for item in items]
        
        return countermeasures
    
    def extract_risk_summary(self) -> Optional[str]:
        """提取风险速览"""
        # 匹配：#### 数字. 风险速览 后面的内容（支持不同的编号）
        pattern = r'####\s*\d+\.\s*风险速览\s*\n(.+?)(?=\n---|\n####|$)'
        match = re.search(pattern, self.content, re.DOTALL)
        if match:
            summary = match.group(1).strip()
            # 清理内容，移除多余的换行和空白
            summary = re.sub(r'\n{3,}', '\n\n', summary)
            # 如果是列表格式，转换为更易读的格式
            summary = summary.replace('- **', '\n- **').replace('**：', '**：')
            return summary.strip()
        return None
    
    def extract_author(self) -> Optional[str]:
        """提取作者署名"""
        # 匹配：作者署名[：:]\s*(.+)（旧格式）
        pattern = r'作者署名[：:]\s*(.+)'
        match = re.search(pattern, self.content)
        if match:
            return match.group(1).strip()
        
        # 匹配：#### 作者署名 后面的内容（新格式）
        pattern = r'####\s*作者署名\s*\n(.+?)(?=\n\d{4}-\d{2}-\d{2}|$)'
        match = re.search(pattern, self.content, re.DOTALL)
        if match:
            author = match.group(1).strip()
            # 提取第一行作为作者
            author = author.split('\n')[0].strip()
            return author
        
        return None
    
    def extract_date(self) -> Optional[str]:
        """提取日期"""
        # 匹配：日期[：:]\s*(\d{4}-\d{2}-\d{2})（旧格式）
        pattern = r'日期[：:]\s*(\d{4}-\d{2}-\d{2})'
        match = re.search(pattern, self.content)
        if match:
            return match.group(1).strip()
        
        # 匹配：#### 作者署名 后面的日期行（新格式：2026-01-16_16-08-49）
        pattern = r'####\s*作者署名\s*\n.*?\n(\d{4}-\d{2}-\d{2}[_\s]\d{2}-\d{2}-\d{2})'
        match = re.search(pattern, self.content, re.DOTALL)
        if match:
            date_str = match.group(1).strip()
            # 将格式转换为标准格式：2026-01-16_16-08-49 -> 2026-01-16
            date_str = date_str.replace('_', ' ').split()[0]
            return date_str
        
        # 匹配文件末尾的日期格式：2026-01-16_16-08-49
        pattern = r'(\d{4}-\d{2}-\d{2})[_\s]\d{2}-\d{2}-\d{2}'
        match = re.search(pattern, self.content)
        if match:
            return match.group(1).strip()
        
        return None
    
    def parse_all(self) -> Dict:
        """
        解析所有内容
        
        返回:
            Dict: 包含所有解析结果的字典
        """
        return {
            '标题': self.extract_title(),
            '风险清单': self.extract_risk_list(),
            '风险详情': self.extract_risk_details(),
            '风险速览': self.extract_risk_summary(),
            '作者': self.extract_author(),
            '日期': self.extract_date(),
            '地理位置关系': self.extract_location_relationships()  # 动态提取的地理位置关系
        }


def print_report_summary(parsed_data: Dict):
    """打印报告摘要"""
    print("=" * 80)
    print(f"报告标题: {parsed_data['标题']}")
    print(f"作者: {parsed_data['作者']}")
    print(f"日期: {parsed_data['日期']}")
    print("=" * 80)
    print()
    
    # 打印风险清单
    print("【风险清单】")
    print("-" * 80)
    risks = parsed_data['风险清单']
    print(f"共发现 {len(risks)} 个风险：")
    print()
    
    for risk in risks:
        print(f"  [{risk['序号']}] {risk['风险名称']}")
        print(f"      类别: {risk['风险类别']}")
        print(f"      等级: {risk['风险等级']}")
        print(f"      描述: {risk['风险描述']}")
        print()
    
    # 打印风险速览
    if parsed_data['风险速览']:
        print("【风险速览】")
        print("-" * 80)
        print(parsed_data['风险速览'])
        print()
    
    # 打印风险统计
    print("【风险统计】")
    print("-" * 80)
    risk_levels = {}
    risk_categories = {}
    
    for risk in risks:
        level = risk['风险等级']
        category = risk['风险类别']
        
        risk_levels[level] = risk_levels.get(level, 0) + 1
        risk_categories[category] = risk_categories.get(category, 0) + 1
    
    print("按风险等级统计：")
    for level, count in sorted(risk_levels.items(), key=lambda x: x[1], reverse=True):
        print(f"  {level}: {count} 个")
    
    print()
    print("按风险类别统计：")
    for category, count in sorted(risk_categories.items(), key=lambda x: x[1], reverse=True):
        print(f"  {category}: {count} 个")
    print()


def load_coordinate_cache() -> Dict:
    """加载坐标缓存文件"""
    cache_file = "coordinate_cache.json"
    if os.path.exists(cache_file):
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                cache = json.load(f)
                # 转换格式：确保所有坐标都是数组格式 [lat, lon]
                normalized_cache = {}
                for key, value in cache.items():
                    if isinstance(value, list) and len(value) >= 2:
                        normalized_cache[key] = [float(value[0]), float(value[1])]
                return normalized_cache
        except Exception as e:
            print(f"警告: 读取坐标缓存失败: {e}")
            return {}
    return {}

def get_location_coords(location: str) -> tuple:
    """获取地理位置的坐标（用于地图标记）"""
    location_coords = {
        '荷兰': (52.1326, 5.2913),
        '中国': (35.8617, 104.1954),
        '日本': (36.2048, 138.2529),
        '美国': (37.0902, -95.7129),
        '欧盟': (50.1109, 8.6821),
        '欧洲': (50.1109, 8.6821),
        '德国': (51.1657, 10.4515),
        '法国': (46.2276, 2.2137),
        '英国': (55.3781, -3.4360),
        '澳大利亚': (-25.2744, 133.7751),
        '韩国': (35.9078, 127.7669),
        '印度': (20.5937, 78.9629),
        '东南亚': (1.3521, 103.8198),
        '沿海地区': (30.0, 120.0),
        '国内': (35.8617, 104.1954),
        '广汽': (23.1291, 113.2644),
        '福岛': (37.75, 140.47),
        '越南': (14.0583, 108.2772),
        '中部': (30.0, 108.0),
        '印度尼西亚': (-0.7893, 113.9213),  # 统一使用完整名称，印尼会映射到这里
        '鹿儿岛': (31.5966, 130.5571),
        '塞梅鲁': (-8.1080, 112.9225),
        '东爪哇': (-7.5361, 112.2384),
        '东莞': (23.0207, 113.7518),
        '安世': (23.0207, 113.7518),
    }
    return location_coords.get(location, (30.0, 120.0))  # 默认坐标

def generate_html_report(parsed_data: Dict, output_file: str):
    """生成HTML格式的报告"""
    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{parsed_data['标题'] or '风险报告'}</title>
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: 'Microsoft YaHei', 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            line-height: 1.6;
            color: #333;
            background: #f5f5f5;
            padding: 20px;
        }}
        
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            padding: 40px;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        
        h1 {{
            color: #2c3e50;
            border-bottom: 3px solid #3498db;
            padding-bottom: 10px;
            margin-bottom: 30px;
        }}
        
        .meta {{
            color: #7f8c8d;
            margin-bottom: 30px;
            font-size: 14px;
        }}
        
        .meta span {{
            margin-right: 20px;
        }}
        
        h2 {{
            color: #34495e;
            margin-top: 40px;
            margin-bottom: 20px;
            padding-left: 10px;
            border-left: 4px solid #3498db;
        }}
        
        h3 {{
            color: #555;
            margin-top: 30px;
            margin-bottom: 15px;
        }}
        
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
            font-size: 14px;
        }}
        
        th, td {{
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }}
        
        th {{
            background: #3498db;
            color: white;
            font-weight: 600;
        }}
        
        tr:hover {{
            background: #f8f9fa;
        }}
        
        .risk-level-high {{
            color: #e74c3c;
            font-weight: bold;
        }}
        
        .risk-level-medium {{
            color: #f39c12;
            font-weight: bold;
        }}
        
        .risk-level-low {{
            color: #27ae60;
            font-weight: bold;
        }}
        
        .risk-detail {{
            margin: 30px 0;
            padding: 20px;
            background: #f8f9fa;
            border-radius: 6px;
            border-left: 4px solid #3498db;
        }}
        
        .risk-detail h4 {{
            color: #2c3e50;
            margin-bottom: 15px;
        }}
        
        .risk-detail p {{
            margin: 10px 0;
        }}
        
        .risk-detail strong {{
            color: #34495e;
        }}
        
        .countermeasures {{
            margin-top: 15px;
        }}
        
        .countermeasures ol {{
            margin-left: 20px;
        }}
        
        .countermeasures li {{
            margin: 8px 0;
        }}
        
        .summary {{
            background: #fff3cd;
            padding: 20px;
            border-radius: 6px;
            border-left: 4px solid #ffc107;
            margin: 30px 0;
        }}
        
        .summary .markdown-content {{
            line-height: 1.8;
        }}
        
        .summary .markdown-content ul {{
            margin: 10px 0;
            padding-left: 25px;
        }}
        
        .summary .markdown-content li {{
            margin: 8px 0;
        }}
        
        .summary .markdown-content strong {{
            color: #856404;
            font-weight: 600;
        }}
        
        .summary .markdown-content p {{
            margin: 10px 0;
        }}
        
        .stats {{
            display: flex;
            gap: 30px;
            margin: 30px 0;
        }}
        
        .stat-box {{
            flex: 1;
            padding: 20px;
            background: #ecf0f1;
            border-radius: 6px;
            text-align: center;
        }}
        
        .stat-box h4 {{
            color: #7f8c8d;
            margin-bottom: 10px;
        }}
        
        .stat-box .number {{
            font-size: 32px;
            font-weight: bold;
            color: #3498db;
        }}
        
        .location-tag {{
            display: inline-block;
            padding: 4px 8px;
            margin: 2px;
            background: #e3f2fd;
            color: #1976d2;
            border-radius: 4px;
            font-size: 12px;
            font-weight: 500;
        }}
        
        .map-container {{
            width: 100%;
            height: 500px;
            margin: 20px 0;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }}
        
        .arrow-marker {{
            background: transparent !important;
            border: none !important;
        }}
        
        .arrowhead {{
            background: transparent !important;
            border: none !important;
        }}
        
        .risk-cards {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
            gap: 20px;
            margin: 30px 0;
        }}
        
        .risk-card {{
            background: white;
            border: 2px solid #e0e0e0;
            border-radius: 8px;
            padding: 20px;
            transition: all 0.3s ease;
            cursor: pointer;
        }}
        
        .risk-card:hover {{
            transform: translateY(-5px);
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
            border-color: #3498db;
        }}
        
        .risk-card.high {{
            border-left: 4px solid #e74c3c;
        }}
        
        .risk-card.medium {{
            border-left: 4px solid #f39c12;
        }}
        
        .risk-card.low {{
            border-left: 4px solid #27ae60;
        }}
        
        .risk-card h4 {{
            margin: 0 0 10px 0;
            color: #2c3e50;
        }}
        
        .risk-card .level {{
            display: inline-block;
            padding: 4px 12px;
            border-radius: 12px;
            font-size: 12px;
            font-weight: bold;
            margin-bottom: 10px;
        }}
        
        .risk-card .level.high {{
            background: #e74c3c;
            color: white;
        }}
        
        .risk-card .level.medium {{
            background: #f39c12;
            color: white;
        }}
        
        .risk-card .level.low {{
            background: #27ae60;
            color: white;
        }}
        
        .view-toggle {{
            display: flex;
            gap: 10px;
            margin: 0;
            margin-left: auto;
        }}
        
        .section-header {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-top: 40px;
            margin-bottom: 20px;
        }}
        
        .section-header h2 {{
            margin: 0 !important;
            padding-left: 10px;
            border-left: 4px solid #3498db;
            color: #34495e;
        }}
        
        .view-toggle button {{
            padding: 10px 20px;
            border: 2px solid #3498db;
            background: white;
            color: #3498db;
            border-radius: 6px;
            cursor: pointer;
            font-size: 14px;
            transition: all 0.3s ease;
        }}
        
        .view-toggle button.active {{
            background: #3498db;
            color: white;
        }}
        
        .view-toggle button:hover {{
            background: #2980b9;
            color: white;
            border-color: #2980b9;
        }}
        
        .view-section {{
            display: none;
        }}
        
        .view-section.active {{
            display: block;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>{parsed_data['标题'] or '风险报告'}</h1>
        
        <div class="meta">
            <span>作者: {parsed_data['作者'] or '未知'}</span>
            <span>日期: {parsed_data['日期'] or '未知'}</span>
        </div>
        
        <h2>1. 风险速览</h2>
'''
    
    # 添加风险速览（使用markdown渲染）
    if parsed_data['风险速览']:
        # 将markdown内容转换为JSON字符串以便安全嵌入HTML
        summary_markdown = json.dumps(parsed_data['风险速览'], ensure_ascii=False)
        html += f'''
        <div class="summary">
            <div class="markdown-content" id="risk-summary-content"></div>
            <script>
                (function() {{
                    const summaryMarkdown = {summary_markdown};
                    const summaryContent = document.getElementById('risk-summary-content');
                    if (summaryContent && typeof marked !== 'undefined') {{
                        summaryContent.innerHTML = marked.parse(summaryMarkdown);
                    }} else if (summaryContent) {{
                        // 如果marked库未加载，显示原始文本
                        summaryContent.textContent = summaryMarkdown;
                    }}
                }})();
            </script>
        </div>
'''
    
    html += '''
        <div class="section-header">
            <h2>2. 风险清单</h2>
            <div class="view-toggle">
                <button data-view="table" class="view-toggle-btn">表格视图</button>
                <button data-view="cards" class="view-toggle-btn">卡片视图</button>
                <button data-view="map" class="view-toggle-btn active">地图视图</button>
            </div>
        </div>
        
        <div id="table-view" class="view-section">
            <table>
                <thead>
                    <tr>
                        <th>序号</th>
                        <th>风险名称</th>
                        <th>风险类别</th>
                        <th>风险等级</th>
                        <th>地理位置</th>
                        <th>风险描述</th>
                    </tr>
                </thead>
                <tbody>
'''
    
    # 添加风险清单表格行
    for risk in parsed_data['风险清单']:
        level_class = f"risk-level-{risk['风险等级'].lower()}" if risk['风险等级'] in ['高', '中', '低'] else ""
        locations = risk.get('地理位置', ['未明确'])
        location_html = ' '.join([f'<span class="location-tag">{loc}</span>' for loc in locations])
        html += f'''
                <tr>
                    <td>{risk['序号']}</td>
                    <td>{risk['风险名称']}</td>
                    <td>{risk['风险类别']}</td>
                    <td class="{level_class}">{risk['风险等级']}</td>
                    <td>{location_html}</td>
                    <td>{risk['风险描述']}</td>
                </tr>
'''
    
    html += '''
            </tbody>
        </table>
        </div>
        
        <div id="cards-view" class="view-section">
            <div class="risk-cards">
'''
    
    # 添加风险卡片
    for risk in parsed_data['风险清单']:
        level = risk['风险等级'].lower()
        level_class = level if level in ['高', '中', '低'] else 'medium'
        locations = risk.get('地理位置', ['未明确'])
        location_html = ' '.join([f'<span class="location-tag">{loc}</span>' for loc in locations])
        html += f'''
                <div class="risk-card {level_class}" onclick="scrollToDetail({risk['序号']})">
                    <h4>{risk['风险名称']}</h4>
                    <div>
                        <span class="level {level_class}">{risk['风险等级']}风险</span>
                    </div>
                    <p style="color: #7f8c8d; font-size: 13px; margin: 10px 0;">
                        <strong>类别：</strong>{risk['风险类别']}
                    </p>
                    <p style="color: #7f8c8d; font-size: 13px; margin: 10px 0;">
                        <strong>地理位置：</strong>{location_html}
                    </p>
                    <p style="color: #555; font-size: 14px; margin-top: 10px;">
                        {risk['风险描述'][:80]}{'...' if len(risk['风险描述']) > 80 else ''}
                    </p>
                </div>
'''
    
    html += '''
            </div>
        </div>
        
        <div id="map-view" class="view-section active">
            <div style="margin-bottom: 10px; display: flex; align-items: center; gap: 10px;">
                <label for="map-style-selector" style="font-size: 14px; color: #555; font-weight: 500;">地图样式：</label>
                <select id="map-style-selector" style="padding: 6px 12px; border: 1px solid #ddd; border-radius: 4px; font-size: 14px; background: white; cursor: pointer; min-width: 200px;">
                    <optgroup label="⭐ 准确地图（推荐）">
                        <option value="osm-china">OpenStreetMap中国</option>
                        <option value="amap-normal">高德地图</option>
                        <option value="tencent-normal">腾讯地图</option>
                    </optgroup>
                    <optgroup label="推荐风格">
                        <option value="cartodb">浅色简洁</option>
                        <option value="cartodb-voyager">彩色风格</option>
                        <option value="cartodb-dark">深色风格</option>
                    </optgroup>
                    <optgroup label="标准地图">
                        <option value="osm">OpenStreetMap（标准）</option>
                        <option value="wikimedia">维基媒体地图</option>
                        <option value="hot">人道主义地图</option>
                    </optgroup>
                    <optgroup label="地形图">
                        <option value="stamen-terrain">Stamen地形图</option>
                        <option value="esri-topo">Esri地形图</option>
                        <option value="opentopomap">OpenTopoMap</option>
                        <option value="esri-physical">Esri物理地图</option>
                        <option value="esri-shaded">Esri阴影地形</option>
                    </optgroup>
                    <optgroup label="特殊风格">
                        <option value="stamen-toner">黑白风格</option>
                        <option value="stamen-watercolor">水彩风格</option>
                        <option value="esri-gray">灰色画布</option>
                        <option value="cyclosm">自行车友好</option>
                    </optgroup>
                    <optgroup label="Esri地图">
                        <option value="esri-street">Esri街道图</option>
                        <option value="esri-satellite">Esri卫星图</option>
                    </optgroup>
                    <optgroup label="其他">
                        <option value="openmapsurfer-roads">道路地图</option>
                        <option value="openmapsurfer-admin">行政边界</option>
                        <option value="thunderforest-landscape">景观地图</option>
                    </optgroup>
                </select>
            </div>
            <div id="risk-map" class="map-container"></div>
        </div>
    '''
    # 添加统计信息
    risks = parsed_data['风险清单']
    risk_levels = {}
    risk_categories = {}
    
    for risk in risks:
        level = risk['风险等级']
        category = risk['风险类别']
        risk_levels[level] = risk_levels.get(level, 0) + 1
        risk_categories[category] = risk_categories.get(category, 0) + 1
    
    html += '''
        <h2>3. 风险统计</h2>
        <div class="stats">
            <div class="stat-box">
                <h4>总风险数</h4>
                <div class="number">''' + str(len(risks)) + '''</div>
            </div>
'''
    
    for level, count in sorted(risk_levels.items(), key=lambda x: x[1], reverse=True):
        html += f'''
            <div class="stat-box">
                <h4>{level}风险</h4>
                <div class="number">{count}</div>
            </div>
'''
    
    html += '''
        </div>
        
        <div class="stats">
'''
    
    for category, count in sorted(risk_categories.items(), key=lambda x: x[1], reverse=True):
        html += f'''
            <div class="stat-box">
                <h4>{category}</h4>
                <div class="number">{count}</div>
            </div>
'''
    
    # 生成风险数据JSON
    risk_data_json = json.dumps([{
        '序号': r['序号'],
        '风险名称': r['风险名称'],
        '风险等级': r['风险等级'],
        '地理位置': r.get('地理位置', ['未明确']),
        '风险描述': r['风险描述']
    } for r in parsed_data['风险清单']], ensure_ascii=False)
    
    # 加载坐标缓存并传递给前端
    coordinate_cache = load_coordinate_cache()
    coordinate_cache_json = json.dumps(coordinate_cache, ensure_ascii=False)
    
    # 获取动态提取的地理位置关系
    location_relationships = parsed_data.get('地理位置关系', {})
    location_relationships_json = json.dumps(location_relationships, ensure_ascii=False)
    
    html += f'''
        </div>
    </div>
    
    <script>
        // 风险数据
        const riskData = {risk_data_json};
        
        // 坐标缓存（从coordinate_cache.json加载）
        const coordinateCache = {coordinate_cache_json};
        
        // 动态提取的地理位置关系（从报告文本中提取）
        const dynamicLocationRelationships = {location_relationships_json};
        
        // 规范化地理位置名称（与后端保持一致）
        function normalizeLocation(location) {{
            // 模糊地区（应该过滤）
            const vagueLocations = ['中部', '沿海地区', '国内', '海外', '东南亚', '广汽', '本田', '安世'];
            if (vagueLocations.includes(location)) {{
                return null;
            }}
            
            // 缩写映射
            const abbreviationMap = {{
                '印尼': '印度尼西亚',
                '欧盟': '欧洲'
            }};
            
            return abbreviationMap[location] || location;
        }}
        
        // 获取坐标的函数（先查缓存，再查预设，最后调用API）
        async function getLocationCoords(location) {{
            // 规范化地理位置
            const normalized = normalizeLocation(location);
            if (!normalized) {{
                return null; // 模糊地区，不获取坐标
            }}
            
            // 1. 先查缓存（使用规范化后的名称）
            if (coordinateCache[normalized]) {{
                return coordinateCache[normalized];
            }}
            
            // 也检查原始名称的缓存（兼容性）
            if (coordinateCache[location]) {{
                return coordinateCache[location];
            }}
            
            // 2. 查预设坐标（只保留规范化后的名称）
            const presetCoords = {{
                '荷兰': [52.1326, 5.2913],
                '中国': [35.8617, 104.1954],
                '日本': [36.2048, 138.2529],
                '美国': [37.0902, -95.7129],
                '欧洲': [50.1109, 8.6821],
                '德国': [51.1657, 10.4515],
                '法国': [46.2276, 2.2137],
                '英国': [55.3781, -3.4360],
                '澳大利亚': [-25.2744, 133.7751],
                '韩国': [35.9078, 127.7669],
                '印度': [20.5937, 78.9629],
                '越南': [14.0583, 108.2772],
                '印度尼西亚': [-0.7893, 113.9213],
                '福岛': [37.75, 140.47],
                '鹿儿岛': [31.5966, 130.5571],
                '塞梅鲁': [-8.1080, 112.9225],
                '东爪哇': [-7.5361, 112.2384],
                '东莞': [23.0207, 113.7518],
            }};
            
            if (presetCoords[normalized]) {{
                return presetCoords[normalized];
            }}
            
            // 3. 调用Nominatim API获取坐标（使用规范化后的名称）
            try {{
                const url = `https://nominatim.openstreetmap.org/search?q=${{encodeURIComponent(normalized)}}&format=json&limit=1&accept-language=zh-CN,zh,en`;
                const response = await fetch(url, {{
                    headers: {{
                        'User-Agent': 'SupplyChainRiskVisualization/1.0'
                    }}
                }});
                
                if (response.ok) {{
                    const data = await response.json();
                    if (data && data.length > 0) {{
                        const coords = [parseFloat(data[0].lat), parseFloat(data[0].lon)];
                        // 保存到缓存（仅内存中，不持久化，使用规范化名称）
                        coordinateCache[normalized] = coords;
                        return coords;
                    }}
                }}
            }} catch (error) {{
                console.warn(`获取 ${{normalized}} 的坐标失败:`, error);
            }}
            
            // 默认坐标
            return [30.0, 120.0];
        }}
        
        // 视图切换函数
        function showView(viewType, buttonElement) {{
            console.log('切换视图:', viewType); // 调试信息
            
            // 隐藏所有视图
            const viewSections = document.querySelectorAll('.view-section');
            if (viewSections.length === 0) {{
                console.warn('未找到.view-section元素');
                return;
            }}
            viewSections.forEach(section => {{
                section.classList.remove('active');
            }});
            
            // 更新所有按钮状态
            const toggleBtns = document.querySelectorAll('.view-toggle-btn');
            toggleBtns.forEach(btn => {{
                btn.classList.remove('active');
            }});
            
            // 显示选中的视图
            const targetView = document.getElementById(viewType + '-view');
            if (targetView) {{
                targetView.classList.add('active');
                console.log('已显示视图:', viewType + '-view'); // 调试信息
            }} else {{
                console.warn('未找到视图元素: ' + viewType + '-view');
                return;
            }}
            
            // 激活被点击的按钮
            if (buttonElement) {{
                buttonElement.classList.add('active');
            }} else {{
                // 如果没有传递buttonElement，通过viewType找到对应的按钮
                toggleBtns.forEach(btn => {{
                    if (btn.getAttribute('data-view') === viewType) {{
                        btn.classList.add('active');
                    }}
                }});
            }}
            
            // 如果是地图视图，延迟初始化地图（确保DOM已更新）
            if (viewType === 'map') {{
                setTimeout(function() {{
                    initMap();
                }}, 100);
            }}
        }}
        
        // 确保函数在全局作用域中可用（用于兼容性）
        window.showView = showView;
        
        // 使用事件监听器绑定视图切换按钮（更可靠的方式）
        function initViewToggle() {{
            const toggleBtns = document.querySelectorAll('.view-toggle-btn');
            console.log('找到视图切换按钮数量:', toggleBtns.length); // 调试信息
            
            if (toggleBtns.length === 0) {{
                console.warn('未找到视图切换按钮，将在100ms后重试');
                setTimeout(initViewToggle, 100);
                return;
            }}
            
            toggleBtns.forEach(btn => {{
                // 添加事件监听器（使用once选项避免重复绑定）
                btn.addEventListener('click', function(e) {{
                    e.preventDefault();
                    const viewType = this.getAttribute('data-view');
                    console.log('按钮被点击，视图类型:', viewType); // 调试信息
                    if (viewType) {{
                        showView(viewType, this);
                    }} else {{
                        console.error('按钮缺少data-view属性');
                    }}
                }}, {{ once: false }});
            }});
        }}
        
        // 如果DOM已加载，立即执行；否则等待DOMContentLoaded
        if (document.readyState === 'loading') {{
            document.addEventListener('DOMContentLoaded', function() {{
                initViewToggle();
                // 如果地图视图是默认显示的，初始化地图
                initMapIfNeeded();
            }});
        }} else {{
            // DOM已经加载完成，立即执行
            setTimeout(function() {{
                initViewToggle();
                // 如果地图视图是默认显示的，初始化地图
                initMapIfNeeded();
            }}, 0);
        }}
        
        // 检查是否需要初始化地图（如果地图视图是默认显示的）
        function initMapIfNeeded() {{
            const mapView = document.getElementById('map-view');
            if (mapView && mapView.classList.contains('active')) {{
                setTimeout(function() {{
                    initMap();
                }}, 200); // 延迟一点确保DOM完全渲染
            }}
        }}
        
        // 初始化地图（修复检查逻辑+增加错误处理）
        function initMap() {{
            const mapContainer = document.getElementById('risk-map');
            // 更严谨的地图初始化检查：判断是否已有Leaflet地图实例
            if (!mapContainer || mapContainer._leaflet_id) {{
                return; // 容器不存在 或 地图已初始化
            }}
            
            // 检查Leaflet库是否加载
            if (typeof L === 'undefined') {{
                console.error('Leaflet地图库未加载！');
                mapContainer.innerHTML = '<div style="padding: 20px; color: red;">地图库加载失败，请刷新页面</div>';
                return;
            }}
            
            // 创建地图
            const map = L.map('risk-map').setView([30, 120], 3);
            
            // 地图样式配置（可以选择不同的地图背景）
            const mapStyles = {{
                // 默认：OpenStreetMap（标准街道地图）
                'osm': {{
                    url: 'https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png',
                    attribution: '© OpenStreetMap contributors',
                    maxZoom: 19
                }},
                // CartoDB Positron（浅色简洁风格，适合数据可视化）
                'cartodb': {{
                    url: 'https://{{s}}.basemaps.cartocdn.com/light_all/{{z}}/{{x}}/{{y}}{{r}}.png',
                    attribution: '© OpenStreetMap contributors © CARTO',
                    maxZoom: 19
                }},
                // CartoDB Dark Matter（深色风格）
                'cartodb-dark': {{
                    url: 'https://{{s}}.basemaps.cartocdn.com/dark_all/{{z}}/{{x}}/{{y}}{{r}}.png',
                    attribution: '© OpenStreetMap contributors © CARTO',
                    maxZoom: 19
                }},
                // Stamen Terrain（地形图）
                'stamen-terrain': {{
                    url: 'https://stamen-tiles-{{s}}.a.ssl.fastly.net/terrain/{{z}}/{{x}}/{{y}}{{r}}.png',
                    attribution: 'Map tiles by Stamen Design, under CC BY 3.0. Data by OpenStreetMap, under ODbL.',
                    maxZoom: 18
                }},
                // Stamen Toner（黑白风格）
                'stamen-toner': {{
                    url: 'https://stamen-tiles-{{s}}.a.ssl.fastly.net/toner/{{z}}/{{x}}/{{y}}{{r}}.png',
                    attribution: 'Map tiles by Stamen Design, under CC BY 3.0. Data by OpenStreetMap, under ODbL.',
                    maxZoom: 18
                }},
                // Esri WorldStreetMap（Esri街道地图）
                'esri-street': {{
                    url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{{z}}/{{y}}/{{x}}',
                    attribution: 'Tiles © Esri',
                    maxZoom: 19
                }},
                // Esri WorldImagery（卫星图）
                'esri-satellite': {{
                    url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}',
                    attribution: 'Tiles © Esri',
                    maxZoom: 19
                }},
                // Esri WorldTopoMap（地形图）
                'esri-topo': {{
                    url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{{z}}/{{y}}/{{x}}',
                    attribution: 'Tiles © Esri',
                    maxZoom: 19
                }},
                // OpenTopoMap（地形图，欧洲数据较好）
                'opentopomap': {{
                    url: 'https://{{s}}.tile.opentopomap.org/{{z}}/{{x}}/{{y}}.png',
                    attribution: 'Map data: © OpenStreetMap contributors, SRTM | Map style: © OpenTopoMap (CC-BY-SA)',
                    maxZoom: 17
                }},
                // CartoDB Voyager（彩色风格，适合展示）
                'cartodb-voyager': {{
                    url: 'https://{{s}}.basemaps.cartocdn.com/rastertiles/voyager/{{z}}/{{x}}/{{y}}{{r}}.png',
                    attribution: '© OpenStreetMap contributors © CARTO',
                    maxZoom: 19
                }},
                // Wikimedia Maps（维基媒体地图）
                'wikimedia': {{
                    url: 'https://maps.wikimedia.org/osm-intl/{{z}}/{{x}}/{{y}}.png',
                    attribution: '© OpenStreetMap contributors, under ODbL',
                    maxZoom: 19
                }},
                // CyclOSM（自行车友好地图）
                'cyclosm': {{
                    url: 'https://{{s}}.tile-cyclosm.openstreetmap.fr/cyclosm/{{z}}/{{x}}/{{y}}.png',
                    attribution: '© OpenStreetMap contributors, Style: CyclOSM',
                    maxZoom: 20
                }},
                // Humanitarian OpenStreetMap（人道主义地图）
                'hot': {{
                    url: 'https://{{s}}.tile.openstreetmap.fr/hot/{{z}}/{{x}}/{{y}}.png',
                    attribution: '© OpenStreetMap contributors, Tiles style by HOT',
                    maxZoom: 19
                }},
                // OpenMapSurfer Roads（道路地图）
                'openmapsurfer-roads': {{
                    url: 'https://korona.geog.uni-heidelberg.de/tiles/roads/x={{x}}&y={{y}}&z={{z}}',
                    attribution: 'Imagery from GIScience Research Group @ University of Heidelberg | Map data © OpenStreetMap contributors',
                    maxZoom: 20
                }},
                // OpenMapSurfer Admin Boundaries（行政边界地图）
                'openmapsurfer-admin': {{
                    url: 'https://korona.geog.uni-heidelberg.de/tiles/adminb/x={{x}}&y={{y}}&z={{z}}',
                    attribution: 'Imagery from GIScience Research Group @ University of Heidelberg | Map data © OpenStreetMap contributors',
                    maxZoom: 20
                }},
                // Esri WorldPhysical（物理地图）
                'esri-physical': {{
                    url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Physical_Map/MapServer/tile/{{z}}/{{y}}/{{x}}',
                    attribution: 'Tiles © Esri',
                    maxZoom: 8
                }},
                // Esri WorldShadedRelief（阴影地形图）
                'esri-shaded': {{
                    url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Shaded_Relief/MapServer/tile/{{z}}/{{y}}/{{x}}',
                    attribution: 'Tiles © Esri',
                    maxZoom: 13
                }},
                // Esri WorldGrayCanvas（灰色画布，简洁风格）
                'esri-gray': {{
                    url: 'https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{{z}}/{{y}}/{{x}}',
                    attribution: 'Tiles © Esri',
                    maxZoom: 16
                }},
                // Stamen Watercolor（水彩风格，艺术感）
                'stamen-watercolor': {{
                    url: 'https://stamen-tiles-{{s}}.a.ssl.fastly.net/watercolor/{{z}}/{{x}}/{{y}}.jpg',
                    attribution: 'Map tiles by Stamen Design, under CC BY 3.0. Data by OpenStreetMap, under ODbL.',
                    maxZoom: 18
                }},
                // Thunderforest Landscape（景观地图）
                'thunderforest-landscape': {{
                    url: 'https://{{s}}.tile.opencyclemap.org/landscape/{{z}}/{{x}}/{{y}}.png',
                    attribution: '© OpenStreetMap contributors, © Thunderforest',
                    maxZoom: 18
                }},
                // OpenWeatherMap（天气地图风格）
                'openweather': {{
                    url: 'https://{{s}}.tile.openweathermap.org/map/temp_new/{{z}}/{{x}}/{{y}}.png?appid=YOUR_API_KEY',
                    attribution: '© OpenWeatherMap',
                    maxZoom: 19
                }},
                // Jawg Streets（Jawg街道地图）
                'jawg-streets': {{
                    url: 'https://{{s}}.tile.jawg.io/jawg-streets/{{z}}/{{x}}/{{y}}{{r}}.png?access-token=YOUR_ACCESS_TOKEN',
                    attribution: '© Jawg Maps © OpenStreetMap contributors',
                    maxZoom: 22
                }},
                // Mapbox Streets（需要API密钥，这里提供模板）
                'mapbox-streets': {{
                    url: 'https://api.mapbox.com/styles/v1/mapbox/streets-v11/tiles/{{z}}/{{x}}/{{y}}?access_token=YOUR_MAPBOX_TOKEN',
                    attribution: '© Mapbox © OpenStreetMap contributors',
                    maxZoom: 22
                }},
                // Mapbox Satellite（卫星图，需要API密钥）
                'mapbox-satellite': {{
                    url: 'https://api.mapbox.com/styles/v1/mapbox/satellite-v9/tiles/{{z}}/{{x}}/{{y}}?access_token=YOUR_MAPBOX_TOKEN',
                    attribution: '© Mapbox © OpenStreetMap contributors',
                    maxZoom: 22
                }},
                // ========== 更准确的地图服务（推荐用于中国区域） ==========
                // 高德地图（Amap）- 中国区域最准确
                // 注意：高德地图的瓦片服务可能需要API密钥，这里提供公开可用的版本
                'amap-normal': {{
                    url: 'https://webrd0{{s}}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={{x}}&y={{y}}&z={{z}}',
                    attribution: '© 高德地图',
                    maxZoom: 18,
                    subdomains: '1234'
                }},
                // 高德地图卫星图
                'amap-satellite': {{
                    url: 'https://webst0{{s}}.is.autonavi.com/appmaptile?style=6&x={{x}}&y={{y}}&z={{z}}',
                    attribution: '© 高德地图',
                    maxZoom: 18,
                    subdomains: '1234'
                }},
                // 天地图（国家基础地理信息中心）- 中国官方地图服务，最准确
                // 注意：需要申请密钥，但提供公开的基础服务
                'tianditu-vec': {{
                    url: 'https://t{{s}}.tianditu.gov.cn/DataServer?T=vec_w&x={{x}}&y={{y}}&l={{z}}&tk=YOUR_TIANDITU_KEY',
                    attribution: '© 国家基础地理信息中心',
                    maxZoom: 18,
                    subdomains: '01234567'
                }},
                // 天地图影像
                'tianditu-img': {{
                    url: 'https://t{{s}}.tianditu.gov.cn/DataServer?T=img_w&x={{x}}&y={{y}}&l={{z}}&tk=YOUR_TIANDITU_KEY',
                    attribution: '© 国家基础地理信息中心',
                    maxZoom: 18,
                    subdomains: '01234567'
                }},
                // 阿里云Datav地图（已在代码中使用，边界准确）
                'aliyun-datav': {{
                    url: 'https://geo.datav.aliyun.com/areas_v3/bound/{{code}}_full.json',
                    attribution: '© 阿里云Datav',
                    maxZoom: 18,
                    isVector: true // 这是矢量数据，需要特殊处理
                }},
                // OpenStreetMap China（OSM中国镜像，边界更准确）
                'osm-china': {{
                    url: 'https://tile.openstreetmap.cn/{{z}}/{{x}}/{{y}}.png',
                    attribution: '© OpenStreetMap contributors (China Mirror)',
                    maxZoom: 19
                }},
                // 腾讯地图（Tencent Map）
                'tencent-normal': {{
                    url: 'https://rt{{s}}.map.gtimg.com/realtimerender?z={{z}}&x={{x}}&y={{y}}&type=vector&style=0',
                    attribution: '© 腾讯地图',
                    maxZoom: 18,
                    subdomains: '0123'
                }},
                // 百度地图（Baidu Map）- 需要坐标转换
                'baidu-normal': {{
                    url: 'https://shangetu{{s}}.map.bdimg.com/it/u=x={{x}};y={{y}};z={{z}};v=009;type=sate&fm=46',
                    attribution: '© 百度地图',
                    maxZoom: 18,
                    subdomains: '0123',
                    crs: 'BD09' // 百度坐标系，需要转换
                }}
            }};
            
            // 选择地图样式（可以修改这里来切换不同的地图背景）
            // 推荐使用更准确的地图服务：'osm-china', 'amap-normal', 'tencent-normal'
            const defaultMapStyle = 'cartodb-voyager'; // 默认使用彩色风格（CartoDB Voyager）
            
            // 创建地图图层的函数
            function createTileLayer(styleKey) {{
                const mapStyle = mapStyles[styleKey] || mapStyles['osm-china'];
                
                // 构建图层配置
                const layerOptions = {{
                    attribution: mapStyle.attribution,
                    maxZoom: mapStyle.maxZoom || 19
                }};
                
                // 处理子域名配置
                if (mapStyle.subdomains) {{
                    layerOptions.subdomains = mapStyle.subdomains;
                }} else {{
                    // 默认子域名
                    layerOptions.subdomains = 'abc';
                }}
                
                // 检查是否需要特殊处理（如矢量数据、坐标系转换等）
                if (mapStyle.isVector) {{
                    console.warn('矢量地图服务需要特殊处理，暂不支持:', styleKey);
                    // 回退到标准OSM
                    return L.tileLayer(mapStyles['osm-china'].url, layerOptions);
                }}
                
                // 检查是否需要API密钥
                if (mapStyle.url && mapStyle.url.includes('YOUR_')) {{
                    console.warn('该地图服务需要API密钥:', styleKey);
                    // 回退到OSM中国
                    return L.tileLayer(mapStyles['osm-china'].url, layerOptions);
                }}
                
                return L.tileLayer(mapStyle.url, layerOptions);
            }}
            
            // 添加默认地图图层
            let currentTileLayer = createTileLayer(defaultMapStyle);
            currentTileLayer.addTo(map);
            
            // 地图样式切换功能
            const mapStyleSelector = document.getElementById('map-style-selector');
            if (mapStyleSelector) {{
                // 设置默认选中值
                mapStyleSelector.value = defaultMapStyle;
                
                // 监听样式切换
                mapStyleSelector.addEventListener('change', function(e) {{
                    const newStyle = e.target.value;
                    if (newStyle && mapStyles[newStyle]) {{
                        // 移除旧图层
                        map.removeLayer(currentTileLayer);
                        // 添加新图层
                        currentTileLayer = createTileLayer(newStyle);
                        currentTileLayer.addTo(map);
                        console.log('地图样式已切换为:', newStyle);
                    }}
                }});
            }}
            
            // 风险等级颜色映射
            const levelColors = {{
                '高': '#e74c3c',
                '中': '#f39c12',
                '低': '#27ae60'
            }};
            
            // 国家名称映射（中文 -> 英文名称，只包含真正的国家，排除国家团体）
            const countryNameMapping = {{
                '中国': 'China',
                '日本': 'Japan',
                '美国': 'United States of America',
                '德国': 'Germany',
                '法国': 'France',
                '英国': 'United Kingdom',
                '荷兰': 'Netherlands',
                '澳大利亚': 'Australia',
                '韩国': 'South Korea',
                '印度': 'India',
                '越南': 'Vietnam',
                '印度尼西亚': 'Indonesia'
            }};
            
            // 国家级别的地理位置（只包含真正的国家，排除国家团体如欧盟、欧洲）
            const countryLevelLocations = [
                '中国', '日本', '美国', '德国', '法国', '英国', '荷兰', 
                '澳大利亚', '韩国', '印度', '越南', '印度尼西亚'
            ];
            
            // 国家团体列表（不进行高亮）
            const countryGroups = ['欧洲', '欧盟', '东南亚'];
            
            // 地区到国家的映射（用于将具体地区映射到所属国家，以便高亮国家）
            const regionToCountry = {{
                // 日本的具体地区
                '鹿儿岛': '日本',
                '福岛': '日本',
                // 印尼的具体地区
                '东爪哇': '印度尼西亚',
                '塞梅鲁': '印度尼西亚',
                // 中国的具体地区
                '东莞': '中国',
                // 德国的具体地区
                '莱茵河': '德国'
            }};
            
            // 地区到地区的映射（子地区 -> 父地区）
            // 当同时存在子地区和父地区时，视为同一个地区，不需要箭头
            // 手动配置的关系（作为补充）
            const manualRegionToRegion = {{
                '塞梅鲁': '东爪哇'  // 塞梅鲁火山属于东爪哇省
            }};
            
            // 合并动态关系和手动配置的关系（动态关系优先）
            const regionToRegion = {{...manualRegionToRegion, ...dynamicLocationRelationships}};
            
            // 获取地理位置对应的国家（如果是地区，返回所属国家；如果是国家，返回国家本身）
            function getCountryFromLocation(location) {{
                // 如果是国家，直接返回
                if (countryLevelLocations.includes(location) && !countryGroups.includes(location)) {{
                    return location;
                }}
                // 如果是地区，返回所属国家
                if (regionToCountry[location]) {{
                    return regionToCountry[location];
                }}
                // 否则返回null
                return null;
            }}
            
            // 检查两个地理位置是否应该被视为同一个地区（因为它们有父子关系）
            function areLocationsSameRegion(loc1, loc2) {{
                // 如果两个位置相同，视为同一地区
                if (loc1 === loc2) {{
                    return true;
                }}
                // 检查是否有父子关系
                // loc1 是 loc2 的子地区
                if (regionToRegion[loc1] === loc2) {{
                    return true;
                }}
                // loc2 是 loc1 的子地区
                if (regionToRegion[loc2] === loc1) {{
                    return true;
                }}
                // 检查是否都映射到同一个父地区
                if (regionToRegion[loc1] && regionToRegion[loc2] && regionToRegion[loc1] === regionToRegion[loc2]) {{
                    return true;
                }}
                return false;
            }}
            
            // 添加地图图例
            const legend = L.control({{position: 'bottomright'}});
            legend.onAdd = function(map) {{
                const div = L.DomUtil.create('div', 'map-legend');
                div.style.backgroundColor = 'white';
                div.style.padding = '10px';
                div.style.borderRadius = '5px';
                div.style.boxShadow = '0 2px 8px rgba(0,0,0,0.2)';
                div.style.fontFamily = "'Microsoft YaHei', sans-serif";
                div.style.fontSize = '12px';
                div.innerHTML = `
                    <div style="font-weight: bold; margin-bottom: 8px; color: #2c3e50;">风险等级</div>
                    <div style="display: flex; align-items: center; margin: 5px 0;">
                        <div style="width: 12px; height: 12px; border-radius: 50%; background: #e74c3c; border: 2px solid #fff; margin-right: 8px;"></div>
                        <span>高风险</span>
                    </div>
                    <div style="display: flex; align-items: center; margin: 5px 0;">
                        <div style="width: 10px; height: 10px; border-radius: 50%; background: #f39c12; border: 2px solid #fff; margin-right: 8px;"></div>
                        <span>中风险</span>
                    </div>
                    <div style="display: flex; align-items: center; margin: 5px 0;">
                        <div style="width: 8px; height: 8px; border-radius: 50%; background: #27ae60; border: 2px solid #fff; margin-right: 8px;"></div>
                        <span>低风险</span>
                `;
                return div;
            }};
            legend.addTo(map);
            
            // 获取单个国家的GeoJSON边界数据（借鉴main.py的实现方式）
            async function loadCountryGeoJSON(countryNameEn) {{
                // 国家名称的多种可能匹配方式
                const nameVariants = {{
                    'Netherlands': ['Netherlands', 'The Netherlands', 'NLD', 'Holland'],
                    'China': ['China', "People's Republic of China", 'CHN', 'PRC'],
                    'Japan': ['Japan', 'JPN'],
                    'United States of America': ['United States of America', 'United States', 'USA', 'US'],
                    'Germany': ['Germany', 'DEU', 'DE'],
                    'France': ['France', 'FRA', 'FR'],
                    'United Kingdom': ['United Kingdom', 'UK', 'GBR', 'GB'],
                    'Australia': ['Australia', 'AUS', 'AU'],
                    'South Korea': ['South Korea', 'Korea', 'KOR', 'KR'],
                    'India': ['India', 'IND', 'IN'],
                    'Vietnam': ['Vietnam', 'VNM', 'VN'],
                    'Indonesia': ['Indonesia', 'IDN', 'ID']
                }};
                
                // 台湾的各种可能名称（用于合并到中国）
                const taiwanVariants = ['Taiwan', 'Taiwan, Province of China', 'Republic of China', 'TWN', 'TW'];
                
                const countryVariants = nameVariants[countryNameEn] || [countryNameEn];
                
                // 使用多个可靠的GeoJSON数据源（借鉴main.py，优先使用阿里云Datav）
                const geojsonUrls = [
                    'https://geo.datav.aliyun.com/areas_v3/bound/geojson?code=all',
                    'https://geo.datav.aliyun.com/areas/bound/geojson?code=all',
                    'https://raw.githubusercontent.com/datasets/geo-boundaries-world-110m/master/countries.geojson',
                    'https://raw.githubusercontent.com/datasets/geo-countries/master/data/countries.geojson',
                    'https://raw.githubusercontent.com/holtzy/D3-graph-gallery/master/DATA/world.geojson',
                    'https://raw.githubusercontent.com/johan/world.geo.json/master/countries.geo.json'
                ];
                
                for (const url of geojsonUrls) {{
                    try {{
                        const response = await fetch(url, {{
                            headers: {{
                                'User-Agent': 'SupplyChainRiskVisualization/1.0'
                            }}
                        }});
                        
                        if (response.ok) {{
                            const worldGeoJson = await response.json();
                            let mainFeature = null;
                            let taiwanFeature = null;
                            
                            // 在GeoJSON中查找指定国家
                            for (const feature of worldGeoJson.features || []) {{
                                const props = feature.properties || {{}};
                                
                                // 查找主国家
                                if (!mainFeature) {{
                                    for (const variant of countryVariants) {{
                                        if (props.NAME === variant || 
                                            props.NAME_LONG === variant ||
                                            props.NAME_EN === variant ||
                                            props.name === variant ||
                                            props.NAME_ISO === variant ||
                                            props.ISO_A3 === variant ||
                                            props.ADMIN === variant ||
                                            props.admin === variant ||
                                            props.ISO_A3_EH === variant ||
                                            props.ADM0_A3 === variant) {{
                                            mainFeature = feature;
                                            break;
                                        }}
                                    }}
                                }}
                                
                                // 如果是中国，同时查找台湾
                                if (countryNameEn === 'China' && !taiwanFeature) {{
                                    for (const variant of taiwanVariants) {{
                                        if (props.NAME === variant || 
                                            props.NAME_LONG === variant ||
                                            props.NAME_EN === variant ||
                                            props.name === variant ||
                                            props.ISO_A3 === variant ||
                                            props.ADMIN === variant) {{
                                            taiwanFeature = feature;
                                            break;
                                        }}
                                    }}
                                }}
                            }}
                            
                            // 如果找到主国家，尝试合并台湾（针对中国）
                            if (mainFeature) {{
                                if (countryNameEn === 'China' && taiwanFeature) {{
                                    // 合并中国和台湾的几何数据
                                    const mergedFeature = JSON.parse(JSON.stringify(mainFeature));
                                    const mainGeom = mergedFeature.geometry || {{}};
                                    const taiwanGeom = taiwanFeature.geometry || {{}};
                                    
                                    // 如果主几何是Polygon，转换为MultiPolygon
                                    if (mainGeom.type === 'Polygon') {{
                                        mainGeom.type = 'MultiPolygon';
                                        mainGeom.coordinates = [mainGeom.coordinates];
                                    }}
                                    
                                    // 添加台湾的几何到MultiPolygon中
                                    if (mainGeom.type === 'MultiPolygon') {{
                                        if (taiwanGeom.type === 'Polygon') {{
                                            mainGeom.coordinates.push(taiwanGeom.coordinates);
                                        }} else if (taiwanGeom.type === 'MultiPolygon') {{
                                            mainGeom.coordinates.push(...taiwanGeom.coordinates);
                                        }}
                                    }}
                                    
                                    return mergedFeature;
                                }} else {{
                                    return mainFeature;
                                }}
                            }}
                        }}
                    }} catch (error) {{
                        continue; // 尝试下一个URL
                    }}
                }}
                
                return null;
            }}
            
            // 获取国家边界GeoJSON并高亮显示
            async function highlightCountries(countries) {{
                if (!countries || countries.length === 0) return;
                
                // 收集需要高亮的国家（排除国家团体）
                const countriesToHighlight = new Set();
                countries.forEach(country => {{
                    // 排除国家团体
                    if (countryGroups.includes(country)) {{
                        return;
                    }}
                    // 只处理真正的国家
                    if (countryLevelLocations.includes(country) && countryNameMapping[country]) {{
                        countriesToHighlight.add(country);
                    }}
                }});
                
                if (countriesToHighlight.size === 0) return;
                
                // 为每个国家加载GeoJSON并高亮
                const highlightPromises = Array.from(countriesToHighlight).map(async (countryName) => {{
                    const countryNameEn = countryNameMapping[countryName];
                    if (!countryNameEn) return;
                    
                    // 加载国家边界GeoJSON数据
                    const countryFeature = await loadCountryGeoJSON(countryNameEn);
                    
                    if (!countryFeature) {{
                        console.warn(`未找到 ${{countryName}} (${{countryNameEn}}) 的GeoJSON边界数据`);
                        return;
                    }}
                    
                    // 计算该国家的最高风险等级和风险数量
                    let maxRiskLevel = '低';
                    let riskCount = 0;
                    const countryRisks = [];
                    
                    riskData.forEach(risk => {{
                        const riskLocations = risk['地理位置'] || [];
                        const riskLocationsArray = typeof riskLocations === 'string' 
                            ? riskLocations.split(',').map(l => l.trim())
                            : riskLocations;
                        
                        // 检查是否包含该国家（包括规范化后的名称和地区映射）
                        const normalizedLocations = riskLocationsArray.map(loc => normalizeLocation(loc)).filter(Boolean);
                        let belongsToCountry = false;
                        
                        // 直接检查是否包含该国家
                        if (normalizedLocations.includes(countryName)) {{
                            belongsToCountry = true;
                        }} else {{
                            // 检查是否有地区映射到该国家
                            normalizedLocations.forEach(loc => {{
                                const mappedCountry = getCountryFromLocation(loc);
                                if (mappedCountry === countryName) {{
                                    belongsToCountry = true;
                                }}
                            }});
                        }}
                        
                        if (belongsToCountry) {{
                            riskCount++;
                            countryRisks.push(risk);
                            const level = risk['风险等级'] || '低';
                            if (level === '高') {{
                                maxRiskLevel = '高';
                            }} else if (level === '中' && maxRiskLevel !== '高') {{
                                maxRiskLevel = '中';
                            }}
                        }}
                    }});
                    
                    const highlightColor = levelColors[maxRiskLevel] || '#95a5a6';
                    
                    // 根据风险等级设置透明度和边框宽度（借鉴main.py）
                    let fillOpacity, borderOpacity, weight;
                    if (maxRiskLevel === '高') {{
                        fillOpacity = 0.15;
                        borderOpacity = 1.0;
                        weight = 3;
                    }} else if (maxRiskLevel === '中') {{
                        fillOpacity = 0.12;
                        borderOpacity = 1.0;
                        weight = 2.5;
                    }} else {{
                        fillOpacity = 0.1;
                        borderOpacity = 1.0;
                        weight = 2;
                    }}
                    
                    // 创建高亮层
                    const highlightLayer = L.geoJSON(countryFeature, {{
                        style: {{
                            fillColor: highlightColor,
                            fillOpacity: fillOpacity,
                            color: highlightColor,
                            weight: weight,
                            opacity: borderOpacity
                        }}
                    }}).addTo(map);
                    
                    // 构建弹窗内容
                    let popupContent = `
                        <div style="font-family: 'Microsoft YaHei', sans-serif; max-width: 300px;">
                            <h4 style="margin: 0 0 8px 0; color: ${{highlightColor}};">${{countryName}}</h4>
                            <p style="margin: 5px 0;"><strong>风险事件数：</strong>${{riskCount}}</p>
                            <p style="margin: 5px 0;"><strong>最高风险等级：</strong><span style="color: ${{highlightColor}};">${{maxRiskLevel}}</span></p>
                    `;
                    
                    if (countryRisks.length > 0) {{
                        popupContent += '<hr style="margin: 8px 0; border: none; border-top: 1px solid #ddd;">';
                        countryRisks.forEach(risk => {{
                            const riskColor = levelColors[risk['风险等级']] || '#95a5a6';
                            popupContent += `
                                <div style="margin-bottom: 8px; padding: 6px; background: #f8f9fa; border-radius: 4px; border-left: 3px solid ${{riskColor}};">
                                    <div style="font-weight: 600; color: ${{riskColor}}; font-size: 12px; margin-bottom: 2px;">${{risk['风险名称'] || '未知风险'}}</div>
                                    <div style="font-size: 11px; color: #666;">${{risk['风险描述'] ? risk['风险描述'].substring(0, 50) + '...' : '无描述'}}</div>
                                </div>
                            `;
                        }});
                    }}
                    
                    popupContent += '</div>';
                    highlightLayer.bindPopup(popupContent);
                }});
                
                // 等待所有国家高亮完成
                await Promise.all(highlightPromises);
            }}
            
            // 添加风险标记（按地理位置分组，多地理位置用箭头连接）
            if (Array.isArray(riskData)) {{
                const locationGroups = {{}}; // 按地理位置分组的风险
                const multiLocationRisks = []; // 多地理位置的风险（需要箭头）
                const allLocationCoords = {{}}; // 所有地理位置的坐标缓存
                const allCountries = new Set(); // 收集所有国家
                
                // 第一步：处理所有风险，分组和识别多地理位置风险
                riskData.forEach(risk => {{
                    // 兼容地理位置：字符串转数组
                    let locations = risk['地理位置'] || ['未明确'];
                    if (typeof locations === 'string') {{
                        locations = locations.split(',').map(item => item.trim());
                    }}
                    
                    // 过滤和规范化地理位置
                    const validLocations = [];
                    locations.forEach(loc => {{
                        if (loc && loc !== '未明确') {{
                            const normalized = normalizeLocation(loc);
                            if (normalized) {{
                                validLocations.push(normalized);
                                // 获取该地理位置对应的国家（如果是地区，映射到所属国家）
                                const country = getCountryFromLocation(normalized);
                                if (country) {{
                                    allCountries.add(country);
                                }}
                            }}
                        }}
                    }});
                    
                    if (validLocations.length === 0) {{
                        return; // 跳过无效地理位置
                    }}
                    
                    // 判断是单地理位置还是多地理位置
                    if (validLocations.length === 1) {{
                        // 单地理位置：按地理位置分组
                        const location = validLocations[0];
                        if (!locationGroups[location]) {{
                            locationGroups[location] = [];
                        }}
                        locationGroups[location].push(risk);
                    }} else {{
                        // 多地理位置：检查是否属于同一个地区
                        // 如果所有地理位置都属于同一个地区（有父子关系），则合并为单地理位置
                        let shouldMerge = false;
                        let mergedLocation = null;
                        
                        if (validLocations.length === 2) {{
                            const loc1 = validLocations[0];
                            const loc2 = validLocations[1];
                            
                            // 检查两个地理位置是否属于同一个地区
                            if (areLocationsSameRegion(loc1, loc2)) {{
                                shouldMerge = true;
                                // 优先使用父地区（如果存在）
                                if (regionToRegion[loc1]) {{
                                    mergedLocation = regionToRegion[loc1];
                                }} else if (regionToRegion[loc2]) {{
                                    mergedLocation = regionToRegion[loc2];
                                }} else {{
                                    // 如果都是子地区且映射到同一个父地区，使用父地区
                                    mergedLocation = regionToRegion[loc1] || loc1;
                                }}
                            }}
                        }}
                        
                        if (shouldMerge && mergedLocation) {{
                            // 合并为单地理位置
                            if (!locationGroups[mergedLocation]) {{
                                locationGroups[mergedLocation] = [];
                            }}
                            locationGroups[mergedLocation].push(risk);
                        }} else {{
                            // 多地理位置：使用箭头连接
                            multiLocationRisks.push({{
                                risk: risk,
                                locations: validLocations
                            }});
                        }}
                    }}
                }});
                
                // 高亮显示发生风险的国家
                highlightCountries(Array.from(allCountries));
                
                // 第二步：获取所有需要的地理位置坐标
                const allLocations = new Set();
                Object.keys(locationGroups).forEach(loc => allLocations.add(loc));
                multiLocationRisks.forEach(item => {{
                    item.locations.forEach(loc => allLocations.add(loc));
                }});
                
                const coordPromises = Array.from(allLocations).map(location => 
                    getLocationCoords(location).then(coords => {{
                        allLocationCoords[location] = coords;
                        return {{ location, coords }};
                    }})
                );
                
                // 第三步：等待所有坐标获取完成，然后创建标记和箭头
                Promise.all(coordPromises).then(() => {{
                    const markers = [];
                    
                    // 为每个地理位置创建标记点（合并该位置的所有风险）
                    Object.keys(locationGroups).forEach(location => {{
                        const risks = locationGroups[location];
                        const coords = allLocationCoords[location];
                        if (!coords || risks.length === 0) return;
                        
                        // 确定该位置的风险等级（取最高等级）
                        const levels = risks.map(r => r['风险等级'] || '未知');
                        const maxLevel = levels.includes('高') ? '高' : (levels.includes('中') ? '中' : '低');
                        const color = levelColors[maxLevel] || '#95a5a6';
                        
                        // 创建标记
                        const marker = L.circleMarker(coords, {{
                            radius: maxLevel === '高' ? 14 : maxLevel === '中' ? 12 : 10,
                            fillColor: color,
                            color: '#fff',
                            weight: 2,
                            opacity: 1,
                            fillOpacity: 0.8
                        }}).addTo(map);
                        
                        markers.push(marker);
                        
                        // 构建弹窗内容（显示该位置的所有风险）
                        let popupContent = `
                            <div style="font-family: 'Microsoft YaHei', sans-serif; max-width: 300px;">
                                <h4 style="margin: 0 0 10px 0; color: ${{color}};">${{location}}</h4>
                                <p style="margin: 5px 0; font-size: 12px; color: #666;">共 ${{risks.length}} 个风险事件</p>
                                <hr style="margin: 10px 0; border: none; border-top: 1px solid #ddd;">
                        `;
                        
                        risks.forEach((risk, idx) => {{
                            const riskColor = levelColors[risk['风险等级']] || '#95a5a6';
                            popupContent += `
                                <div style="margin-bottom: 12px; padding: 8px; background: #f8f9fa; border-radius: 4px; border-left: 3px solid ${{riskColor}};">
                                    <div style="font-weight: 600; color: ${{riskColor}}; margin-bottom: 4px;">${{risk['风险名称'] || '未知风险'}}</div>
                                    <div style="font-size: 11px; color: #666;">${{risk['风险描述'] || '无描述'}}</div>
                                </div>
                            `;
                        }});
                        
                        popupContent += '</div>';
                        marker.bindPopup(popupContent);
                    }});
                    
                    // 为多地理位置风险创建箭头
                    multiLocationRisks.forEach(item => {{
                        const {{ risk, locations }} = item;
                        if (locations.length < 2) return;
                        
                        // 获取所有位置的坐标
                        const coordsList = locations.map(loc => allLocationCoords[loc]).filter(c => c !== null && c !== undefined);
                        if (coordsList.length < 2) return;
                        
                        // 对于两个地理位置，创建箭头从主体（第一个位置）指向客体（第二个位置）
                        // locations[0] 是主体，locations[1] 是客体
                        const fromCoords = coordsList[0]; // 主体位置（起点）
                        const toCoords = coordsList[1]; // 客体位置（终点，箭头指向这里）
                        
                        const level = risk['风险等级'] || '未知';
                        const color = levelColors[level] || '#95a5a6';
                        
                        // 计算箭头方向角度（从主体指向客体）
                        // dx: 经度差（东正西负），dy: 纬度差（北正南负）
                        const dx = toCoords[1] - fromCoords[1]; // 经度差
                        const dy = toCoords[0] - fromCoords[0]; // 纬度差
                        // Math.atan2(dy, dx) 计算从起点到终点的角度（弧度），转换为度数
                        const angle = Math.atan2(dy, dx) * 180 / Math.PI;
                        const angleRad = angle * Math.PI / 180;
                        
                        // 箭头头的大小（像素）
                        const arrowheadSize = 10; // 箭头头大小，适中即可
                        
                        // 使用Leaflet的坐标转换来计算箭头头偏移
                        // 将地理坐标转换为容器像素坐标
                        const fromPoint = map.latLngToContainerPoint(fromCoords);
                        const toPoint = map.latLngToContainerPoint(toCoords);
                        
                        // 计算方向向量（归一化）
                        const distancePx = Math.sqrt((toPoint.x - fromPoint.x) ** 2 + (toPoint.y - fromPoint.y) ** 2);
                        const unitX = (toPoint.x - fromPoint.x) / distancePx;
                        const unitY = (toPoint.y - fromPoint.y) / distancePx;
                        
                        // 箭头头的尺寸
                        const arrowheadLengthPx = arrowheadSize * 2; // 箭头头长度（从底部到尖端）
                        const lineWeight = 3; // 箭头线宽度
                        const arrowheadBaseWidth = lineWeight * 1.8; // 箭头头底部宽度（略大于线宽，确保覆盖，比例更协调）
                        
                        // 计算箭头头底部中心的位置（从终点往回推箭头头长度）
                        // 这是箭头头底部中心应该在地图上的位置
                        const arrowheadBasePoint = {{
                            x: toPoint.x - unitX * arrowheadLengthPx,
                            y: toPoint.y - unitY * arrowheadLengthPx
                        }};
                        
                        // 将箭头头底部中心位置转换回地理坐标
                        const arrowheadBaseCoords = map.containerPointToLatLng(arrowheadBasePoint);
                        
                        // 创建箭头线（从起点延伸到目标位置，箭头头会覆盖在线的末端）
                        // 线延伸到toCoords，箭头头覆盖在末端，底部中心在arrowheadBaseCoords
                        const arrow = L.polyline([fromCoords, toCoords], {{
                            color: color,
                            weight: lineWeight, // 线宽
                            opacity: 0.7,
                            lineCap: 'round', // 圆角端点，使连接更平滑
                            lineJoin: 'round'
                        }}).addTo(map);
                        
                        // 在箭头中点添加标记点显示风险信息
                        const midLat = (fromCoords[0] + toCoords[0]) / 2;
                        const midLon = (fromCoords[1] + toCoords[1]) / 2;
                        const midMarker = L.marker([midLat, midLon], {{
                            icon: L.divIcon({{
                                className: 'arrow-marker',
                                html: `<div style="background: ${{color}}; color: white; padding: 4px 8px; border-radius: 4px; font-size: 11px; white-space: nowrap; box-shadow: 0 2px 4px rgba(0,0,0,0.3); text-align: center;">${{risk['风险名称']}}</div>`,
                                iconSize: [120, 20],
                                iconAnchor: [60, 10]
                            }})
                        }}).addTo(map);
                        
                        // 添加箭头头
                        // 箭头头设计：尖端在SVG的(arrowheadTipX, arrowheadTipY)，底部中心在(-arrowheadLengthPx, arrowheadTipY)
                        // 锚点在尖端(arrowheadTipX, arrowheadTipY)，位置在toCoords（目标位置/客体位置）
                        // 箭头方向：从主体（locations[0]）指向客体（locations[1]）
                        // 这样尖端会精确在toCoords（客体），底部中心会在arrowheadBaseCoords，正好与线连接
                        // 线延伸到toCoords，箭头头覆盖在线的末端，确保完全连接
                        const svgSize = arrowheadLengthPx * 2 + 4; // SVG容器大小，留边距（需要容纳从-arrowheadLengthPx到arrowheadLengthPx的范围）
                        const arrowheadTipX = arrowheadLengthPx; // 箭头头尖端X坐标（相对于SVG中心）
                        const arrowheadTipY = arrowheadSize; // 箭头头尖端Y坐标（SVG垂直中心）
                        const arrowheadBaseX = -arrowheadLengthPx; // 箭头头底部中心X坐标（从尖端往回推，指向主体方向）
                        const arrowheadBaseY = arrowheadTipY; // 箭头头底部中心Y坐标（与尖端同Y）
                        const arrowheadBaseHalfWidth = arrowheadBaseWidth * 2; // 箭头头底部半宽
                        
                        // 创建箭头头marker，锚点在尖端，位置在toCoords（客体位置）
                        // 箭头方向：从主体（fromCoords）指向客体（toCoords）
                        // 这样尖端精确指向toCoords（客体），底部中心会在arrowheadBaseCoords（指向主体方向）
                        // 线延伸到toCoords，箭头头覆盖在线的末端，底部中心正好在线的终点位置，确保完全连接
                        const arrowhead = L.marker(toCoords, {{
                            icon: L.divIcon({{
                                className: 'arrowhead',
                                html: `<svg width="${{svgSize}}" height="${{arrowheadSize * 2}}" style="transform: rotate(${{angle}}deg); transform-origin: ${{arrowheadTipX}}px ${{arrowheadTipY}}px; pointer-events: none;">
                                    <polygon points="${{arrowheadBaseX}},${{arrowheadBaseY - arrowheadBaseHalfWidth}} ${{arrowheadTipX}},${{arrowheadTipY}} ${{arrowheadBaseX}},${{arrowheadBaseY + arrowheadBaseHalfWidth}}" 
                                        fill="${{color}}" 
                                        stroke="#ffffff" 
                                        stroke-width="1.5" 
                                        stroke-linejoin="round"
                                        stroke-linecap="round"
                                        opacity="0.95"
                                        style="filter: drop-shadow(0px 1px 2px rgba(0,0,0,0.3));" />
                                </svg>`,
                                iconSize: [svgSize, arrowheadSize * 2],
                                iconAnchor: [arrowheadTipX, arrowheadTipY] // 锚点在箭头尖端，使尖端精确定位在toCoords
                            }})
                        }}).addTo(map);
                        
                        markers.push(arrow, midMarker, arrowhead);
                        
                        // 添加弹窗
                        const popupContent = `
                            <div style="font-family: 'Microsoft YaHei', sans-serif;">
                                <h4 style="margin: 0 0 10px 0; color: ${{color}};">${{risk['风险名称'] || '未知风险'}}</h4>
                                <p style="margin: 5px 0;"><strong>风险等级：</strong><span style="color: ${{color}};">${{level}}</span></p>
                                <p style="margin: 5px 0;"><strong>影响关系：</strong>${{locations[0]}} → ${{locations[1]}}</p>
                                <p style="margin: 5px 0; font-size: 12px; color: #666;">${{risk['风险描述'] || '无描述'}}</p>
                            </div>
                        `;
                        midMarker.bindPopup(popupContent);
                        arrow.bindPopup(popupContent);
                    }});
                    
                    // 调整地图视图
                    if (markers.length > 0) {{
                        const group = new L.featureGroup(markers);
                        map.fitBounds(group.getBounds().pad(0.1));
                    }}
                }});
            }} else {{
                console.error('riskData不是数组格式:', riskData);
            }}
        }}
        
        // 滚动到详情（修复seq参数未使用+增加元素判空）
        function scrollToDetail(seq) {{
            // 根据seq找到对应的详情元素（假设seq是风险的序号，对应DOM的data-seq属性）
            const detailSection = document.querySelector(`.risk-detail h4[data-seq="${{seq}}"]`);
            if (detailSection) {{
                detailSection.scrollIntoView({{ behavior: 'smooth', block: 'start' }}); 
            }} else {{
                console.warn(`未找到序号为${{seq}}的风险详情`); 
            }}
        }}
        
        // 确保函数在全局作用域中可用（用于onclick属性）
        window.scrollToDetail = scrollToDetail;
        
    </script>
</body>
</html>
'''
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html)
    
    print(f"✓ 已生成HTML报告: {output_file}")


def extract_datetime_from_folder(folder_name: str) -> Dict[str, str]:
    """
    从文件夹名中提取日期和时间信息
    
    参数:
        folder_name: 文件夹名称，格式如 "2026-01-14_20-23-57"
    
    返回:
        Dict: 包含格式化后的日期和时间信息
    """
    # 匹配格式：YYYY-MM-DD_HH-MM-SS 或 YYYY-MM-DD
    pattern = r'(\d{4}-\d{2}-\d{2})(?:_(\d{2})-(\d{2})-(\d{2}))?'
    match = re.match(pattern, folder_name)
    
    if match:
        date_str = match.group(1)  # 日期部分：2026-01-14
        if match.group(2):  # 有时间部分
            hour = match.group(2)
            minute = match.group(3)
            second = match.group(4)
            time_str = f"{hour}:{minute}:{second}"
            datetime_str = f"{date_str} {time_str}"
            datetime_sort = f"{date_str}_{hour}-{minute}-{second}"  # 用于排序
        else:
            time_str = ""
            datetime_str = date_str
            datetime_sort = date_str
        
        return {
            'date': date_str,  # 日期：2026-01-14
            'time': time_str,  # 时间：20:23:57 或空字符串
            'datetime': datetime_str,  # 完整日期时间：2026-01-14 20:23:57
            'datetime_sort': datetime_sort,  # 用于排序：2026-01-14_20-23-57
            'display': datetime_str if time_str else date_str  # 显示文本
        }
    
    # 如果无法解析，返回文件夹名
    return {
        'date': folder_name,
        'time': '',
        'datetime': folder_name,
        'datetime_sort': folder_name,
        'display': folder_name
    }


def batch_generate_reports(reports_dir: str = "reports"):
    """
    批量生成所有报告的HTML文件
    
    参数:
        reports_dir: 报告目录路径
    """
    if not os.path.exists(reports_dir):
        print(f"错误: 报告目录不存在: {reports_dir}")
        return []
    
    report_list = []
    
    # 遍历所有报告文件夹
    for folder_name in os.listdir(reports_dir):
        folder_path = os.path.join(reports_dir, folder_name)
        if not os.path.isdir(folder_path):
            continue
        
        # 查找 research_assessment_manager_report.md
        report_md = os.path.join(folder_path, "research_assessment_manager_report.md")
        if not os.path.exists(report_md):
            continue
        
        try:
            print(f"\n正在处理: {folder_name}")
            print(f"  报告文件: {report_md}")
            
            # 解析报告
            parser = RiskReportParser(report_md)
            parsed_data = parser.parse_all()
            
            # 生成HTML报告
            output_html = os.path.join(folder_path, "report_visualization.html")
            generate_html_report(parsed_data, output_html)
            
            # 收集报告信息
            # 计算相对路径（相对于reports目录的父目录）
            relative_path = os.path.relpath(output_html, os.path.dirname(reports_dir))
            # 统一使用正斜杠（Web标准）
            relative_path = relative_path.replace('\\', '/')
            
            # 从文件夹名中提取完整的日期和时间信息
            datetime_info = extract_datetime_from_folder(folder_name)
            
            # 如果报告中有日期，优先使用报告的日期，但保留文件夹的时间信息
            report_date = parsed_data.get('日期')
            if report_date:
                # 如果报告日期只有日期部分，尝试合并时间
                if '_' not in report_date and datetime_info['time']:
                    # 报告日期格式：2026-01-14，文件夹有时间：20:23:57
                    datetime_info['date'] = report_date
                    datetime_info['datetime'] = f"{report_date} {datetime_info['time']}"
                    datetime_info['display'] = datetime_info['datetime']
            
            title = parsed_data.get('标题') or '未知标题'
            author = parsed_data.get('作者') or '未知'
            
            report_info = {
                'folder': folder_name,
                'title': title,
                'date': datetime_info['date'],  # 日期部分：2026-01-14
                'time': datetime_info['time'],  # 时间部分：20:23:57 或空
                'datetime': datetime_info['datetime'],  # 完整日期时间：2026-01-14 20:23:57
                'datetime_sort': datetime_info['datetime_sort'],  # 用于排序
                'display_date': datetime_info['display'],  # 显示用的日期时间
                'author': author,
                'risk_count': len(parsed_data.get('风险清单', [])),
                'html_path': output_html,
                'relative_path': relative_path
            }
            report_list.append(report_info)
            
            print(f"  ✓ 完成 - 风险数量: {report_info['risk_count']}")
            
        except Exception as e:
            print(f"  ✗ 错误: {e}")
            import traceback
            traceback.print_exc()
            continue
    
    return report_list


def generate_index_html(report_list: List[Dict], output_file: str = "index.html"):
    """
    生成索引页面，包含报告列表和选择功能
    
    参数:
        report_list: 报告信息列表
        output_file: 输出文件路径
    """
    # 按日期时间排序（最新的在前）
    # 使用 datetime_sort 字段进行排序，确保时间顺序正确
    def get_sort_key(report):
        # 优先使用 datetime_sort（包含完整日期时间），其次使用 folder
        return report.get('datetime_sort') or report.get('folder', '')
    
    sorted_reports = sorted(report_list, key=get_sort_key, reverse=True)
    
    # 生成选项HTML
    options_html = ""
    for report in sorted_reports:
        # 使用 display_date（包含完整日期时间）或 datetime 字段
        date_str = report.get('display_date') or report.get('datetime') or report.get('date') or report.get('folder', '未知日期')
        title_str = report.get('title', '未知标题')
        risk_count = report.get('risk_count', 0)
        display_text = f"{date_str} - {title_str} ({risk_count}个风险)"
        # 转义HTML特殊字符
        relative_path = report.get("relative_path", "").replace('\\', '/')
        if relative_path:
            options_html += f'<option value="{relative_path}">{display_text}</option>\n'
    
    # 生成报告数据JSON（用于JavaScript）
    report_data_json = json.dumps(sorted_reports, ensure_ascii=False, indent=2)
    
    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>风险报告可视化 - 索引</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: 'Microsoft YaHei', 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            line-height: 1.6;
            color: #333;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }}
        
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            padding: 40px;
            border-radius: 12px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.2);
        }}
        
        h1 {{
            color: #2c3e50;
            text-align: center;
            margin-bottom: 10px;
            font-size: 32px;
        }}
        
        .subtitle {{
            text-align: center;
            color: #7f8c8d;
            margin-bottom: 40px;
            font-size: 14px;
        }}
        
        .selector-section {{
            margin-bottom: 30px;
            padding: 25px;
            background: #f8f9fa;
            border-radius: 8px;
            border-left: 4px solid #3498db;
        }}
        
        .selector-section label {{
            display: block;
            font-weight: 600;
            color: #34495e;
            margin-bottom: 12px;
            font-size: 16px;
        }}
        
        .selector-section select {{
            width: 100%;
            padding: 12px 15px;
            border: 2px solid #ddd;
            border-radius: 6px;
            font-size: 15px;
            background: white;
            color: #333;
            cursor: pointer;
            transition: all 0.3s ease;
        }}
        
        .selector-section select:hover {{
            border-color: #3498db;
        }}
        
        .selector-section select:focus {{
            outline: none;
            border-color: #3498db;
            box-shadow: 0 0 0 3px rgba(52, 152, 219, 0.1);
        }}
        
        .view-button {{
            display: block;
            width: 100%;
            padding: 14px 20px;
            margin-top: 15px;
            background: #3498db;
            color: white;
            border: none;
            border-radius: 6px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s ease;
            text-align: center;
            text-decoration: none;
        }}
        
        .view-button:hover {{
            background: #2980b9;
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(52, 152, 219, 0.3);
        }}
        
        .view-button:active {{
            transform: translateY(0);
        }}
        
        .iframe-container {{
            margin-top: 30px;
            border: 2px solid #ddd;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            background: white;
            min-height: 600px;
        }}
        
        .iframe-container iframe {{
            width: 100%;
            height: 800px;
            border: none;
            display: block;
        }}
        
        .stats-section {{
            margin-top: 30px;
            padding: 20px;
            background: #ecf0f1;
            border-radius: 8px;
        }}
        
        .stats-section h3 {{
            color: #2c3e50;
            margin-bottom: 15px;
        }}
        
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
        }}
        
        .stat-item {{
            background: white;
            padding: 15px;
            border-radius: 6px;
            text-align: center;
        }}
        
        .stat-item .number {{
            font-size: 28px;
            font-weight: bold;
            color: #3498db;
            margin-bottom: 5px;
        }}
        
        .stat-item .label {{
            font-size: 14px;
            color: #7f8c8d;
        }}
        
        .empty-state {{
            text-align: center;
            padding: 60px 20px;
            color: #95a5a6;
        }}
        
        .empty-state .icon {{
            font-size: 64px;
            margin-bottom: 20px;
        }}
        
        .empty-state p {{
            font-size: 16px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>📊 风险报告可视化</h1>
        <p class="subtitle">选择报告查看详细的风险分析和可视化地图</p>
        
        <div class="selector-section">
            <label for="report-selector">选择报告：</label>
            <select id="report-selector">
                <option value="">-- 请选择报告 --</option>
                {options_html}
            </select>
            <a href="#" id="view-button" class="view-button" style="display: none;">查看报告</a>
        </div>
        
        <div id="iframe-container" class="iframe-container" style="display: none;">
            <iframe id="report-frame" src=""></iframe>
        </div>
        
        <div class="stats-section" id="stats-section" style="display: none;">
            <h3>📈 报告统计</h3>
            <div class="stats-grid">
                <div class="stat-item">
                    <div class="number" id="total-reports">0</div>
                    <div class="label">总报告数</div>
                </div>
                <div class="stat-item">
                    <div class="number" id="total-risks">0</div>
                    <div class="label">总风险数</div>
                </div>
                <div class="stat-item">
                    <div class="number" id="avg-risks">0</div>
                    <div class="label">平均风险数</div>
                </div>
            </div>
        </div>
    </div>
    
    <script>
        const reportData = {report_data_json};
        
        const selector = document.getElementById('report-selector');
        const viewButton = document.getElementById('view-button');
        const iframeContainer = document.getElementById('iframe-container');
        const reportFrame = document.getElementById('report-frame');
        const statsSection = document.getElementById('stats-section');
        
        // 更新统计信息
        function updateStats() {{
            const totalReports = reportData.length;
            const totalRisks = reportData.reduce((sum, r) => sum + (r.risk_count || 0), 0);
            const avgRisks = totalReports > 0 ? Math.round(totalRisks / totalReports) : 0;
            
            document.getElementById('total-reports').textContent = totalReports;
            document.getElementById('total-risks').textContent = totalRisks;
            document.getElementById('avg-risks').textContent = avgRisks;
            
            statsSection.style.display = 'block';
        }}
        
        // 选择报告
        selector.addEventListener('change', function() {{
            const selectedValue = this.value;
            if (selectedValue) {{
                viewButton.style.display = 'block';
                viewButton.href = selectedValue;
                viewButton.textContent = '查看报告 →';
            }} else {{
                viewButton.style.display = 'none';
                iframeContainer.style.display = 'none';
            }}
        }});
        
        // 查看报告
        viewButton.addEventListener('click', function(e) {{
            e.preventDefault();
            const selectedValue = selector.value;
            if (selectedValue) {{
                reportFrame.src = selectedValue;
                iframeContainer.style.display = 'block';
                // 滚动到iframe
                iframeContainer.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
            }}
        }});
        
        // 初始化统计信息
        updateStats();
    </script>
</body>
</html>'''
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html)
    
    print(f"\n✓ 已生成索引页面: {output_file}")


def main():
    """主函数"""
    import sys
    
    # 检查是否有批量处理参数
    if len(sys.argv) > 1 and sys.argv[1] == '--batch':
        # 批量处理模式
        print("=" * 80)
        print("批量生成报告HTML文件")
        print("=" * 80)
        
        report_list = batch_generate_reports()
        
        if report_list:
            print(f"\n{'=' * 80}")
            print(f"批量处理完成！共处理 {len(report_list)} 个报告")
            print(f"{'=' * 80}")
            
            # 生成索引页面
            generate_index_html(report_list)
        else:
            print("\n未找到任何报告文件")
        
        return
    
    # 单个文件处理模式
    if len(sys.argv) > 1:
        report_path = sys.argv[1]
    else:
        report_path = "reports/2026-01-14_20-23-57/research_assessment_manager_report.md"
    
    
    try:
        # 解析报告
        print(f"正在解析报告: {report_path}")
        parser = RiskReportParser(report_path)
        parsed_data = parser.parse_all()
        
        # 打印摘要
        # print_report_summary(parsed_data)
        
        # 生成HTML报告
        output_html = report_path.replace('.md', '_visualization.html').replace('research_assessment_manager_report', 'report')
        generate_html_report(parsed_data, output_html)
        
        print(f"\n解析完成！")
        print(f"  - 风险数量: {len(parsed_data['风险清单'])}")
        print(f"  - 详情数量: {len(parsed_data['风险详情'])}")
        print(f"  - HTML报告: {output_html}")
        
    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
