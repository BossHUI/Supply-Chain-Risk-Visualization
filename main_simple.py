#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
简化版风险报告解析脚本
专注于解析 research_assessment_manager_report.md 格式的报告
"""

import os
import re
from typing import List, Dict, Optional


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
    
    def extract_location_from_text(self, text: str) -> List[str]:
        """
        从文本中提取地理位置信息
        
        参数:
            text: 要分析的文本
        
        返回:
            List[str]: 地理位置列表
        """
        locations = []
        
        # 常见地理位置关键词
        location_keywords = [
            '荷兰', '中国', '日本', '美国', '欧盟', '欧洲', '德国', '法国', '英国',
            '澳大利亚', '韩国', '印度', '东南亚', '沿海地区', '国内', '海外',
            '广汽', '本田', '福岛', '莱茵河', '越南', '中部', '印尼', '印度尼西亚',
            '鹿儿岛', '塞梅鲁', '东爪哇', '东莞', '安世'
        ]
        
        # 从文本中查找地理位置
        for keyword in location_keywords:
            if keyword in text:
                if keyword not in locations:
                    locations.append(keyword)
        
        # 如果没有找到明确位置，尝试从风险速览中提取
        if not locations:
            summary = self.extract_risk_summary()
            if summary:
                for keyword in location_keywords:
                    if keyword in summary:
                        if keyword not in locations:
                            locations.append(keyword)
        
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
            # 提取地理位置
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
            
            risks.append({
                '序号': int(seq.strip()),
                '风险名称': name.strip(),
                '风险类别': category.strip(),
                '风险等级': level.strip(),
                '风险描述': description.strip(),
                '地理位置': locations
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
            '日期': self.extract_date()
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
        import json
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
                <button onclick="showView('table', this)" class="active">表格视图</button>
                <button onclick="showView('cards', this)">卡片视图</button>
                <button onclick="showView('map', this)">地图视图</button>
            </div>
        </div>
        
        <div id="table-view" class="view-section active">
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
        
        <div id="map-view" class="view-section">
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
    import json
    risk_data_json = json.dumps([{
        '序号': r['序号'],
        '风险名称': r['风险名称'],
        '风险等级': r['风险等级'],
        '地理位置': r.get('地理位置', ['未明确']),
        '风险描述': r['风险描述']
    } for r in parsed_data['风险清单']], ensure_ascii=False)
    
    html += f'''
        </div>
    </div>
    
    <script>
        // 风险数据
        const riskData = {risk_data_json};
        
        // 视图切换
        function showView(viewType, buttonElement) {{
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
            const toggleBtns = document.querySelectorAll('.view-toggle button');
            toggleBtns.forEach(btn => {{
                btn.classList.remove('active');
            }});
            
            // 显示选中的视图
            const targetView = document.getElementById(viewType + '-view');
            if (targetView) {{
                targetView.classList.add('active');
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
                    const btnText = btn.textContent.trim();
                    if ((viewType === 'table' && btnText.includes('表格')) ||
                        (viewType === 'cards' && btnText.includes('卡片')) ||
                        (viewType === 'map' && btnText.includes('地图'))) {{
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
            
            // 添加地图图层
            L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{ 
                attribution: '© OpenStreetMap contributors',
                maxZoom: 18
            }}).addTo(map);
            
            // 风险等级颜色映射
            const levelColors = {{
                '高': '#e74c3c',
                '中': '#f39c12',
                '低': '#27ae60'
            }};
            
            // 地理位置坐标映射
            const locationCoords = {{
                '荷兰': [52.1326, 5.2913],
                '中国': [35.8617, 104.1954],
                '日本': [36.2048, 138.2529],
                '美国': [37.0902, -95.7129],
                '欧盟': [50.1109, 8.6821],
                '欧洲': [50.1109, 8.6821],
                '德国': [51.1657, 10.4515],
                '法国': [46.2276, 2.2137],
                '英国': [55.3781, -3.4360],
                '澳大利亚': [-25.2744, 133.7751],
                '韩国': [35.9078, 127.7669],
                '印度': [20.5937, 78.9629],
                '东南亚': [1.3521, 103.8198],
                '沿海地区': [30.0, 120.0],
                '国内': [35.8617, 104.1954],
                '广汽': [23.1291, 113.2644],
                '福岛': [37.75, 140.47],
                '越南': [14.0583, 108.2772],
                '中部': [30.0, 108.0],
            }};
            
            // 添加风险标记（增加错误处理，兼容字符串/数组格式的地理位置）
            if (Array.isArray(riskData)) {{
                riskData.forEach(risk => {{
                    // 兼容地理位置：字符串转数组（如"中国,美国"→["中国","美国"]）
                    let locations = risk['地理位置'] || ['未明确'];
                    if (typeof locations === 'string') {{
                        locations = locations.split(',').map(item => item.trim());
                    }}
                    const level = risk['风险等级'] || '未知';
                    const color = levelColors[level] || '#95a5a6';
                    
                    locations.forEach(location => {{
                        if (!location || location === '未明确') return;
                        const coords = locationCoords[location] || [30.0, 120.0];
                        
                        // 创建标记
                        const marker = L.circleMarker(coords, {{
                            radius: level === '高' ? 12 : level === '中' ? 10 : 8,
                            fillColor: color,
                            color: '#fff',
                            weight: 2,
                            opacity: 1,
                            fillOpacity: 0.8
                        }}).addTo(map);
                        
                        // 添加弹窗
                        const popupContent = `
                            <div style="font-family: 'Microsoft YaHei', sans-serif;">
                                <h4 style="margin: 0 0 10px 0; color: ${{color}};">${{risk['风险名称'] || '未知风险'}}</h4>
                                <p style="margin: 5px 0;"><strong>风险等级：</strong><span style="color: ${{color}};">${{level}}</span></p>
                                <p style="margin: 5px 0;"><strong>地理位置：</strong>${{location}}</p>
                                <p style="margin: 5px 0; font-size: 12px; color: #666;">${{risk['风险描述'] || '无描述'}}</p>
                            </div>
                        `; // 修复4：弹窗里的所有都转义
                        marker.bindPopup(popupContent);
                    }});
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
                detailSection.scrollIntoView({{ behavior: 'smooth', block: 'start' }}); // 修复6：scrollIntoView的参数转义
            }} else {{
                console.warn(`未找到序号为${{seq}}的风险详情`); 
            }}
        }}
    </script>
</body>
</html>
'''
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html)
    
    print(f"✓ 已生成HTML报告: {output_file}")


def main():
    """主函数"""
    import sys
    
    # 默认报告路径
    if len(sys.argv) > 1:
        report_path = sys.argv[1]
    else:
        report_path = "reports/2026-01-14_20-23-57/research_assessment_manager_report.md"
    
    # 检查文件是否存在
    if not os.path.exists(report_path):
        print(f"错误: 报告文件不存在: {report_path}")
        print("用法: python main_simple.py [报告文件路径]")
        return
    
    try:
        # 解析报告
        print(f"正在解析报告: {report_path}")
        parser = RiskReportParser(report_path)
        parsed_data = parser.parse_all()
        
        # 打印摘要
        print_report_summary(parsed_data)
        
        # 生成HTML报告
        output_html = report_path.replace('.md', '_simple.html').replace('research_assessment_manager_report', 'report')
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
