import folium
import pandas as pd
import re
import os
import json
import requests
import time
from openai import OpenAI 
from dotenv import load_dotenv
load_dotenv()

API_KEY = os.getenv("DEEPSEEK_API_KEY")
API_BASE_URL = os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com")

client = OpenAI(
    api_key=API_KEY, 
    base_url=API_BASE_URL 
)

# 坐标缓存文件路径
COORD_CACHE_FILE = "coordinate_cache.json"

def load_coordinate_cache():
    """加载坐标缓存"""
    if os.path.exists(COORD_CACHE_FILE):
        try:
            with open(COORD_CACHE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_coordinate_cache(cache):
    """保存坐标缓存"""
    try:
        with open(COORD_CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"保存坐标缓存失败: {e}")

def geocode_location(location_name, use_cache=True):
    """
    使用Nominatim地理编码API获取地点坐标
    
    参数:
        location_name: 地点名称（支持中文）
        use_cache: 是否使用缓存
    
    返回:
        [纬度, 经度] 或 None
    """
    # 加载缓存
    cache = load_coordinate_cache() if use_cache else {}
    
    # 检查缓存
    if location_name in cache:
        print(f"  使用缓存坐标: {location_name} -> {cache[location_name]}")
        return cache[location_name]
    
    # 使用Nominatim API进行地理编码
    try:
        # Nominatim API要求使用User-Agent，并且有速率限制（每秒1次请求）
        headers = {
            'User-Agent': 'SupplyChainRiskVisualization/1.0'
        }
        
        # 构建查询URL
        url = "https://nominatim.openstreetmap.org/search"
        params = {
            'q': location_name,
            'format': 'json',
            'limit': 1,
            'accept-language': 'zh-CN,zh,en'
        }
        
        print(f"  正在查询坐标: {location_name}...")
        response = requests.get(url, params=params, headers=headers, timeout=10)
        
        # 遵守速率限制
        time.sleep(1)
        
        if response.status_code == 200:
            data = response.json()
            if data and len(data) > 0:
                lat = float(data[0]['lat'])
                lon = float(data[0]['lon'])
                coord = [lat, lon]
                
                # 保存到缓存
                if use_cache:
                    cache[location_name] = coord
                    save_coordinate_cache(cache)
                
                print(f"  ✓ 成功获取坐标: {location_name} -> {coord}")
                return coord
            else:
                print(f"  ✗ 未找到地点: {location_name}")
                return None
        else:
            print(f"  ✗ 地理编码API请求失败: HTTP {response.status_code}")
            return None
            
    except Exception as e:
        print(f"  ✗ 地理编码失败 ({location_name}): {e}")
        return None

def get_location_coord(location_name, country_coords=None, coord_corrections=None, use_geocoding=True):
    """
    获取地点坐标（优先级：修正表 > 国家字典 > 地理编码API）
    
    参数:
        location_name: 地点名称
        country_coords: 国家坐标字典
        coord_corrections: 坐标修正字典
        use_geocoding: 是否使用地理编码API
    
    返回:
        [纬度, 经度] 或 None
    """
    # 1. 优先检查坐标修正表（城市/地区）
    if coord_corrections and location_name in coord_corrections:
        return coord_corrections[location_name]
    
    # 2. 检查国家坐标字典
    if country_coords and location_name in country_coords:
        return country_coords[location_name]
    
    # 3. 使用地理编码API自动获取
    if use_geocoding:
        return geocode_location(location_name)
    
    return None

class RiskReportParser:
    def __init__(self, file_path, use_geocoding=True):
        self.file_path = file_path
        self.content = self._load_file()
        self.use_geocoding = use_geocoding
        # 预设国家中心点坐标（报告仅提供国名时使用，作为缓存和备用）
        self.country_coords = {
            "荷兰": [52.1326, 5.2913],
            "中国": [35.8617, 104.1954],
            "日本": [36.2048, 138.2529],
            "美国": [37.0902, -95.7129]
        }
        # 坐标修正表（已知城市的正确坐标）
        self.coord_corrections = {
            "日本福岛": [37.75, 140.47],
            "福岛": [37.75, 140.47],
            "越南中部": [15.0, 108.0],
            "德国莱茵河流域": [50.0, 8.0],
            "莱茵河": [50.0, 8.0]
        }

    def _load_file(self):
        if not os.path.exists(self.file_path):
            raise FileNotFoundError(f"未找到报告文件: {self.file_path}")
        with open(self.file_path, 'r', encoding='utf-8') as f:
            return f.read()

    def parse_dms(self, dms_str):
        """解析度分秒坐标: N32°4' E118°8' -> [32.066, 118.133]"""
        try:
            lat_match = re.search(r'([NS])(\d+)°(?:(\d+)\')?', dms_str)
            lon_match = re.search(r'([EW])(\d+)°(?:(\d+)\')?', dms_str)
            
            def convert(match):
                direction, degree, minute = match.groups()
                val = float(degree) + (float(minute)/60 if minute else 0)
                return -val if direction in ['S', 'W'] else val
            
            return [convert(lat_match), convert(lon_match)]
        except:
            return None

    def extract_gdp_table(self):
        """提取地缘政治中断概率表"""
        # 匹配表格行：| 荷兰 | 3 | 12 | [10, 14] |
        pattern = r'\| ([\u4e00-\u9fa5\w]+) +\| (\d+) +\| (\d+) +\|'
        matches = re.findall(pattern, self.content)
        data = []
        for loc, base, current in matches:
            # 自动获取坐标（优先使用缓存和预设，失败则使用地理编码API）
            coord = get_location_coord(
                loc, 
                country_coords=self.country_coords,
                coord_corrections=self.coord_corrections,
                use_geocoding=self.use_geocoding
            )
            
            if coord:
                data.append({
                    "location": loc,
                    "coord": coord,
                    "gdp": int(current)
                })
            else:
                print(f"警告: 无法获取 {loc} 的坐标，跳过该地点")
        return data

    def extract_ndp_table(self):
        """提取自然灾变综合概率表"""
        # 匹配：| 地震 | 4.2 | 日本福岛（N32°4' E118°8'） | 38% |
        # 更宽松的匹配模式，支持不同的空格和格式
        pattern = r'\| ([\u4e00-\u9fa5]+)\s+\|\s+([\d\.]+)\s+\|\s+([^（]+)（([^）]+)）\s+\|\s+([\d%]+)\s+\|'
        matches = re.findall(pattern, self.content)
        
        data = []
        for hazard, prob, city, dms, contrib in matches:
            city_clean = city.strip()
            
            # 优先解析度分秒坐标
            coord = self.parse_dms(dms)
            
            # 如果度分秒解析失败，尝试从坐标修正表或地理编码API获取
            if not coord:
                coord = get_location_coord(
                    city_clean,
                    country_coords=self.country_coords,
                    coord_corrections=self.coord_corrections,
                    use_geocoding=self.use_geocoding
                )
            
            if coord:
                data.append({
                    "hazard": hazard,
                    "prob": float(prob),
                    "city": city_clean,
                    "coord": coord,
                    "contrib": contrib
                })
            else:
                print(f"警告: 无法获取 {city_clean} 的坐标，跳过该地点")
        return data

    def get_overall_risk(self):
        """提取整体风险等级"""
        match = re.search(r'ER\d [低中高]', self.content)
        return match.group(0) if match else "未知"
    
    def extract_gdp_overall(self):
        """从报告中提取整体GDP值（如7.5%）"""
        # 匹配：当前GDP整体为**7.5%**
        pattern = r'当前GDP整体为\*\*([\d\.]+)%\*\*'
        match = re.search(pattern, self.content)
        if match:
            return float(match.group(1))
        return None
    
    def extract_ndp_overall(self):
        """从报告中提取整体NDP值（如9.5%）"""
        # 匹配：当前NDP为**9.5%**
        pattern = r'当前NDP为\*\*([\d\.]+)%\*\*'
        match = re.search(pattern, self.content)
        if match:
            return float(match.group(1))
        return None
    
    def extract_ndp_confidence_interval(self):
        """提取NDP置信区间"""
        # 匹配：**9.5%**（95%置信区间：[8.2%, 10.8%]）
        pattern = r'95%置信区间：\[([\d\.]+)%, ([\d\.]+)%\]'
        match = re.search(pattern, self.content)
        if match:
            return [float(match.group(1)), float(match.group(2))]
        return None

    def extract_with_llm(self):
        """利用 LLM 语义化提取数据"""
        system_prompt = """
        你是一个供应链风险数据提取专家。请从报告中提取风险指标并输出为标准的 JSON 格式。
        
        要求提取以下数据：
        1. gdp_data: 数组，每个元素包括 location (国名), current_gdp (当前估算值%, 纯数字), key_risk (核心风险点描述)。
        2. ndp_data: 数组，每个元素包括 hazard (灾种), city (区域名称), dms_coord (坐标, 如 N32°4' E118°8'), probability (概率%, 纯数字), contribution (贡献度%, 如 "38%")。
        3. overall_risk: 报告判定的风险等级 (如 "ER2 中")。
        4. gdp_overall: 报告中的整体GDP值 (如 7.5，纯数字，不带%)。
        5. ndp_overall: 报告中的整体NDP值 (如 9.5，纯数字，不带%)。
        6. ndp_confidence_interval: NDP的置信区间 [下限, 上限]，如 [8.2, 10.8]。
        
        注意：
        - 如果报告中包含坐标文本，请原样提取。
        - 如果仅有国名，请在 location 中指明。
        - 确保提取的是报告中明确给出的整体值，而不是计算的平均值。
        请只输出 JSON，不要有任何多余解释。
        """
        print("正在通过 LLM 提取结构化风险数据...")
        try:
            response = client.chat.completions.create(
                model="deepseek-chat", 
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": self.content}
                ],
                response_format={ "type": "json_object" }
            )
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            print(f"LLM 提取失败: {e}，将回退到正则表达式方法")
            return None

def get_risk_color(risk_level):
    """根据风险等级返回颜色"""
    # 提取 ER 等级（如 ER1, ER2, ER3）
    er_match = re.search(r'ER(\d+)', str(risk_level))
    if er_match:
        er_num = er_match.group(1)
        colors = {
            "1": "#27ae60",  # 绿色
            "2": "#f1c40f",  # 黄色
            "3": "#e74c3c"   # 红色
        }
        return colors.get(er_num, "#95a5a6")
    
    # 如果没有 ER 等级，根据文字判断
    if "低" in str(risk_level):
        return "#27ae60"
    elif "中" in str(risk_level):
        return "#f1c40f"
    elif "高" in str(risk_level):
        return "#e74c3c"
    return "#95a5a6"  # 默认灰色

def hex_to_folium_color(hex_color):
    """将十六进制颜色值转换为 folium Icon 支持的颜色名称"""
    # folium Icon 支持的颜色列表
    color_map = {
        "#e74c3c": "red",           # 红色
        "#3498db": "blue",          # 蓝色
        "#27ae60": "green",         # 绿色
        "#f1c40f": "orange",        # 黄色/橙色
        "#e67e22": "orange",        # 橙色
        "#95a5a6": "gray",          # 灰色
        "#2c3e50": "darkblue",      # 深蓝色
        "#34495e": "darkblue",      # 深蓝灰色
    }
    # 转换为小写并查找映射
    hex_color_lower = hex_color.lower()
    return color_map.get(hex_color_lower, "red")  # 默认返回红色

def create_info_icon(concept_key):
    """为关键概念创建带信息图标和悬停提示的HTML"""
    # 定义关键概念及其说明
    concept_definitions = {
        "overall_risk": {
            "title": "整体风险评级 (ER)",
            "content": "基于GDP和NDP综合评估的整体风险等级。<br><br><span style='color: #27ae60;'>● ER1 低</span> - GDP&lt;5% 且 NDP&lt;7%<br><span style='color: #f1c40f;'>● ER2 中</span> - GDP 5-15% 或 NDP 7-20%<br><span style='color: #e74c3c;'>● ER3 高</span> - GDP&gt;15% 且 NDP&gt;20%"
        },
        "gdp": {
            "title": "地缘政治中断概率 (GDP)",
            "content": "Geopolitical Disruption Probability，表示因地缘政治因素导致供应链中断≥24小时的概率。包括贸易冲突、制裁、政治不稳定等因素。"
        },
        "ndp": {
            "title": "自然灾变综合概率 (NDP)",
            "content": "Natural Disaster Probability，表示因自然灾害导致供应链中断≥24小时的概率。包括地震、台风、洪水等自然灾害风险。"
        },
        "confidence_interval": {
            "title": "95%置信区间",
            "content": "统计学概念，表示在95%的置信水平下，真实值落在此区间的概率。置信区间越窄，表示估算越精确。"
        },
        "risk_value": {
            "title": "风险值",
            "content": "表示特定地区因地缘政治因素导致供应链中断的概率百分比。数值越高，风险越大。<br><br><strong>数值来源：</strong>从风险报告中提取的GDP（地缘政治中断概率）估算值，基于历史数据、当前政治环境和专家评估综合计算得出。"
        },
        "risk_level": {
            "title": "风险等级",
            "content": "根据风险值划分的等级：低风险(<5%)、中风险(5-10%)、高风险(>10%)。用于快速识别风险程度。"
        },
        "probability": {
            "title": "概率",
            "content": "表示未来12个月内因该自然灾害导致供应链中断≥24小时的概率百分比。<br><br><strong>数值来源：</strong>从风险报告中提取的NDP（自然灾变综合概率）数据，基于历史灾害记录、地理环境分析和统计模型计算得出。"
        },
        "contribution": {
            "title": "贡献度",
            "content": "该风险事件对整体NDP的贡献百分比，反映该风险在整体自然灾害风险中的重要性。<br><br><strong>数值来源：</strong>从风险报告中直接提取的贡献度百分比。整体NDP通过联合概率公式计算：NDP = 1 - ∏(1-pi)，其中pi为各风险事件的概率。贡献度表示该风险事件在整体NDP中的占比。"
        }
    }
    
    if concept_key not in concept_definitions:
        return ""
    
    definition = concept_definitions[concept_key]
    # 转义单引号，但保留HTML标签属性中的单引号
    # 使用正则表达式只转义不在HTML标签中的单引号
    import re
    def escape_quotes_except_html_attrs(text):
        # 分割文本，分离HTML标签和文本内容
        parts = re.split(r'(<[^>]+>)', text)
        result = []
        for part in parts:
            if part.startswith('<'):
                # HTML标签，保留原样（包括属性中的单引号）
                result.append(part)
            else:
                # 文本内容，转义单引号
                result.append(part.replace("'", "&#39;"))
        return ''.join(result)
    
    title_escaped = escape_quotes_except_html_attrs(definition['title'])
    content_escaped = escape_quotes_except_html_attrs(definition['content'])
    
    # 定义不需要动画效果的概念（概览面板中的主要指标，但这些概念在概览面板中已不再显示信息图标）
    static_concepts = ["confidence_interval"]
    # 根据概念类型选择样式类
    icon_class = "info-icon info-icon-static" if concept_key in static_concepts else "info-icon info-icon-animated"
    
    # 定义需要右侧定位的概念（显示在图标左侧，用于最右侧的列，避免被左侧面板遮挡）
    right_positioned_concepts = ["contribution", "risk_level"]
    # 定义需要左侧定位的概念（显示在图标右侧，用于中间列，避免被左侧面板遮挡）
    left_positioned_concepts = ["probability"]
    # 定义需要底部定位的概念（显示在图标下方，用于面板顶部，避免被面板边界遮挡）
    bottom_positioned_concepts = ["overall_risk"]
    # 根据概念类型选择定位类
    if concept_key in right_positioned_concepts:
        tooltip_class = "info-tooltip info-tooltip-right"
    elif concept_key in left_positioned_concepts:
        tooltip_class = "info-tooltip info-tooltip-left"
    elif concept_key in bottom_positioned_concepts:
        tooltip_class = "info-tooltip info-tooltip-bottom"
    else:
        tooltip_class = "info-tooltip"
    
    return f'''<span class="{icon_class}" style="position: relative;">
        i
        <div class="{tooltip_class}" style="bottom: 100%; left: 50%; transform: translateX(-50%) translateY(-5px); margin-bottom: 8px;">
            <div class="info-tooltip-title">{title_escaped}</div>
            <div class="info-tooltip-content">{content_escaped}</div>
        </div>
    </span>'''

def generate_map(report_path, output_html, use_llm=True, use_geocoding=True):
    """
    生成风险可视化地图
    
    参数:
        report_path: 报告文件路径
        output_html: 输出 HTML 文件路径
        use_llm: 是否使用 LLM 提取数据（默认 True），False 则使用正则表达式
        use_geocoding: 是否使用地理编码API自动获取未知地点的坐标（默认 True）
    
    返回:
        bool: 成功返回True，失败返回False
    """
    try:
        parser = RiskReportParser(report_path, use_geocoding=use_geocoding)
    except FileNotFoundError as e:
        print(f"错误: {e}")
        return False
    except Exception as e:
        print(f"初始化解析器失败: {e}")
        return False
    
    # 优先使用 LLM 提取，失败则回退到正则表达式
    gdp_overall = None
    ndp_overall = None
    ndp_confidence_interval = None
    
    if use_llm:
        llm_data = parser.extract_with_llm()
        if llm_data:
            # 使用 LLM 提取的数据
            gdp_list = []
            for item in llm_data.get('gdp_data', []):
                location = item['location']
                # 自动获取坐标（优先使用缓存和预设，失败则使用地理编码API）
                coord = get_location_coord(
                    location,
                    country_coords=parser.country_coords,
                    coord_corrections=parser.coord_corrections,
                    use_geocoding=parser.use_geocoding
                )
                
                if coord:
                    gdp_list.append({
                        "location": location,
                        "coord": coord,
                        "gdp": int(item['current_gdp']),
                        "key_risk": item.get('key_risk', '')
                    })
                else:
                    print(f"警告: 无法获取 {location} 的坐标，跳过该地点")
            
            ndp_list = []
            for item in llm_data.get('ndp_data', []):
                city = item.get('city', '')
                dms_coord = item.get('dms_coord', '')
                
                # 优先解析度分秒坐标
                coord = parser.parse_dms(dms_coord) if dms_coord else None
                
                # 如果度分秒解析失败，尝试从坐标修正表或地理编码API获取
                if not coord:
                    coord = get_location_coord(
                        city,
                        country_coords=parser.country_coords,
                        coord_corrections=parser.coord_corrections,
                        use_geocoding=parser.use_geocoding
                    )
                
                if coord:
                    ndp_list.append({
                        "hazard": item['hazard'],
                        "prob": float(item['probability']),
                        "city": city,
                        "coord": coord,
                        "contrib": item.get('contribution', f"{item['probability']}%")
                    })
                else:
                    print(f"警告: 无法获取 {city} 的坐标，跳过该地点")
            
            overall_risk = llm_data.get('overall_risk', '未知')
            gdp_overall = llm_data.get('gdp_overall')
            ndp_overall = llm_data.get('ndp_overall')
            ndp_confidence_interval = llm_data.get('ndp_confidence_interval')
        else:
            # LLM 提取失败，回退到正则表达式
            print("回退到正则表达式提取方法...")
            gdp_list = parser.extract_gdp_table()
            ndp_list = parser.extract_ndp_table()
            overall_risk = parser.get_overall_risk()
            gdp_overall = parser.extract_gdp_overall()
            ndp_overall = parser.extract_ndp_overall()
            ndp_confidence_interval = parser.extract_ndp_confidence_interval()
    else:
        # 直接使用正则表达式
        gdp_list = parser.extract_gdp_table()
        ndp_list = parser.extract_ndp_table()
        overall_risk = parser.get_overall_risk()
        gdp_overall = parser.extract_gdp_overall()
        ndp_overall = parser.extract_ndp_overall()
        ndp_confidence_interval = parser.extract_ndp_confidence_interval()

    # 初始化地图（使用 CartoDB positron 样式，更清晰）
    m = folium.Map(location=[30, 60], zoom_start=3, tiles='CartoDB positron')
    
    # 添加自定义CSS样式和动画
    custom_css = '''
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
        
        body {
            font-family: 'Inter', 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif !important;
        }
        
        .leaflet-popup-content-wrapper {
            border-radius: 8px !important;
            box-shadow: 0 4px 20px rgba(0,0,0,0.15) !important;
        }
        
        .leaflet-popup-content {
            margin: 0 !important;
            padding: 0 !important;
        }
        
        .leaflet-tooltip {
            background: rgba(255, 255, 255, 0.95) !important;
            border: 1px solid #ddd !important;
            border-radius: 6px !important;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1) !important;
            font-family: 'Inter', 'Segoe UI', sans-serif !important;
        }
        
        /* 滚动条美化 */
        #risk-panel::-webkit-scrollbar {
            width: 8px;
        }
        
        #risk-panel::-webkit-scrollbar-track {
            background: #f1f1f1;
            border-radius: 4px;
        }
        
        #risk-panel::-webkit-scrollbar-thumb {
            background: #888;
            border-radius: 4px;
        }
        
        #risk-panel::-webkit-scrollbar-thumb:hover {
            background: #555;
        }
        
        /* 表格悬停效果 */
        table tbody tr:hover {
            background-color: #f8f9fa !important;
            transition: background-color 0.2s ease;
        }
        
        /* 动画效果 */
        @keyframes fadeIn {
            from {
                opacity: 0;
                transform: translateY(-10px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }
        
        #risk-panel, [style*="position: fixed"][style*="top: 20px"][style*="right: 20px"] {
            animation: fadeIn 0.5s ease-out;
        }
        
        /* 信息图标样式 - 灰色，无动画 */
        .info-icon {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 12px;
            height: 12px;
            border-radius: 50%;
            background-color: #d5dbdb;
            color: white;
            font-size: 11px;
            font-weight: bold;
            cursor: help;
            margin-left: 4px;
            vertical-align: middle;
            position: relative;
            flex-shrink: 0;
            /* 不设置 z-index，避免创建堆叠上下文，让子元素（信息框）的 z-index 生效 */
        }
        
        /* 确保信息框在悬停时显示在信息图标之上 */
        .info-icon:hover {
            z-index: 1;
        }
        
        .info-icon:hover .info-tooltip {
            z-index: 99999 !important;
        }
        
        /* 确保信息框在显示时位于最顶层 */
        .info-icon-animated:hover .info-tooltip,
        .info-icon-static:hover .info-tooltip {
            z-index: 99999 !important;
        }
        
        /* 带动画效果的图标样式 - 用于表格中的概念 */
        .info-icon-animated {
            transition: all 0.2s ease;
        }
        
        .info-icon-animated:hover {
            background-color: #bdc3c7;
            transform: scale(1.1);
        }
        
        /* 无动画效果的图标样式 - 用于概览面板中的主要指标 */
        .info-icon-static:hover {
            background-color: #bdc3c7;
        }
        
        /* 悬停提示框样式 - 带动画效果 */
        .info-tooltip {
            position: absolute;
            background: linear-gradient(135deg, #ffffff 0%, #f8f9fa 100%);
            color: #2c3e50;
            padding: 12px 16px;
            border-radius: 8px;
            font-size: 12px;
            line-height: 1.6;
            width: 280px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.15);
            border: 1px solid #e0e0e0;
            z-index: 99999;
            opacity: 0;
            pointer-events: none;
            white-space: normal;
            word-wrap: break-word;
        }
        
        /* 带动画效果的提示框 */
        .info-icon-animated .info-tooltip {
            transition: opacity 0.3s ease, transform 0.3s ease;
            transform: translateY(-5px);
        }
        
        /* 右侧定位的提示框初始状态 */
        .info-icon-animated .info-tooltip-right {
            transform: translateY(-5px) !important;
        }
        
        /* 左侧定位的提示框初始状态 */
        .info-icon-animated .info-tooltip-left {
            transform: translateX(-50%) translateY(-5px) !important;
        }
        
        /* 底部定位的提示框初始状态 */
        .info-icon-animated .info-tooltip-bottom {
            transform: translateX(-50%) translateY(5px) !important;
        }
        
        .info-icon-animated:hover .info-tooltip {
            opacity: 1;
            transform: translateY(0);
            pointer-events: auto;
        }
        
        /* 右侧定位的提示框在悬停时的transform */
        .info-icon-animated:hover .info-tooltip-right {
            transform: translateY(0) !important;
        }
        
        /* 左侧定位的提示框在悬停时的transform */
        .info-icon-animated:hover .info-tooltip-left {
            transform: translateX(-50%) translateY(0) !important;
        }
        
        /* 底部定位的提示框在悬停时的transform */
        .info-icon-animated:hover .info-tooltip-bottom {
            transform: translateX(-50%) translateY(0) !important;
        }
        
        /* 无动画效果的提示框 - 用于静态图标 */
        .info-icon-static .info-tooltip {
            transition: opacity 0.2s ease;
        }
        
        .info-icon-static:hover .info-tooltip {
            opacity: 1;
            pointer-events: auto;
        }
        
        .info-tooltip::before {
            content: '';
            position: absolute;
            bottom: -6px;
            left: 20px;
            width: 0;
            height: 0;
            border-left: 6px solid transparent;
            border-right: 6px solid transparent;
            border-top: 6px solid #f8f9fa;
        }
        
        .info-tooltip-title {
            font-weight: 600;
            margin-bottom: 6px;
            font-size: 13px;
            color: #2c3e50;
        }
        
        .info-tooltip-content {
            color: #34495e;
            font-size: 11px;
        }
        
        /* 右侧定位的提示框（显示在图标左侧，用于最右侧的列，避免被左侧面板遮挡） */
        .info-tooltip-right {
            bottom: 100% !important;
            right: 0 !important;
            left: auto !important;
            transform: translateY(-5px) !important;
            margin-bottom: 8px;
        }
        
        .info-tooltip-right::before {
            left: auto !important;
            right: 20px !important;
        }
        
        /* 上方偏左定位的提示框（显示在图标上方，稍微偏左，用于中间列，避免被面板边界遮挡） */
        .info-tooltip-left {
            bottom: 100% !important;
            left: 0 !important;
            right: auto !important;
            transform: translateX(-50%) translateY(-5px) !important;
            margin-bottom: 8px;
            width: 240px !important;
        }
        
        .info-tooltip-left::before {
            left: 50% !important;
            right: auto !important;
            top: auto !important;
            bottom: -6px !important;
            border-top: 6px solid #f8f9fa;
            border-bottom: none;
            border-left: 6px solid transparent;
            border-right: 6px solid transparent;
        }
        
        /* 底部定位的提示框（显示在图标下方，用于面板顶部，避免被面板边界遮挡） */
        .info-tooltip-bottom {
            top: 100% !important;
            bottom: auto !important;
            left: 50% !important;
            right: auto !important;
            transform: translateX(-50%) translateY(5px) !important;
            margin-top: 8px;
            margin-bottom: 0;
            width: 240px !important;
        }
        
        .info-tooltip-bottom::before {
            top: -6px !important;
            bottom: auto !important;
            left: 50% !important;
            right: auto !important;
            transform: translateX(-50%);
            border-bottom: 6px solid #f8f9fa;
            border-top: none;
            border-left: 6px solid transparent;
            border-right: 6px solid transparent;
        }
        
        /* 表格标题中的信息图标 */
        th .info-icon {
            margin-left: 4px;
        }
        
        /* 确保表格标题可以包含信息图标 */
        th {
            white-space: nowrap;
        }
        
        /* 禁用 GeoJson 图层的点击高亮边框 */
        .leaflet-interactive {
            cursor: default !important;
        }
        
        .leaflet-interactive:focus {
            outline: none !important;
        }
        
        /* 禁用 GeoJson 图层点击时的边框高亮 */
        path.leaflet-interactive {
            stroke-width: inherit !important;
        }
        
        path.leaflet-interactive:hover,
        path.leaflet-interactive:active,
        path.leaflet-interactive:focus {
            stroke: inherit !important;
            stroke-width: inherit !important;
            outline: none !important;
        }
    </style>
    '''
    m.get_root().html.add_child(folium.Element(custom_css))

    # 计算统计数据用于概览
    # 优先使用报告中的实际整体值，如果没有则计算平均值作为备选
    if gdp_overall is not None:
        avg_gdp = gdp_overall
    else:
        total_gdp = sum(item['gdp'] for item in gdp_list) if gdp_list else 0
        avg_gdp = total_gdp / len(gdp_list) if gdp_list else 0
    
    if ndp_overall is not None:
        total_ndp = ndp_overall
    else:
        # 如果没有整体值，计算联合概率（使用"或"逻辑：1 - ∏(1-pi)）
        if ndp_list:
            total_ndp = 1.0
            for item in ndp_list:
                total_ndp *= (1 - item['prob'] / 100)
            total_ndp = (1 - total_ndp) * 100
        else:
            total_ndp = 0
    
    main_risk_locations = sorted(gdp_list, key=lambda x: x['gdp'], reverse=True)[:2] if gdp_list else []
    main_risk_text = ", ".join([f"{item['location']} (GDP:{item['gdp']}%)" for item in main_risk_locations])

    # 0. 添加有风险国家的边界高亮显示（使用实际国家边界）
    # 国家名称到 GeoJSON 中名称的映射
    country_name_mapping = {
        "荷兰": "Netherlands",
        "中国": "China",
        "日本": "Japan",
        "美国": "United States of America"
    }
    
    # 从在线服务加载国家边界 GeoJSON 数据的函数
    def load_country_geojson(country_name_en):
        """从在线服务加载国家边界 GeoJSON 数据"""
        try:
            # 使用多个可靠的 GeoJSON 数据源，以增强区域的政治一致性
        
            geojson_urls = [
                # 推荐：阿里云Datav提供的全球国家边界（中国及其台湾地区为一体，符合一中原则）
                "https://geo.datav.aliyun.com/areas_v3/bound/geojson?code=all",  # 另一个阿里云Datav版本
                "https://geo.datav.aliyun.com/areas/bound/geojson?code=all",  # 阿里云Datav提供的全球国家边界（推荐给中国国内用户）

                # 以下为国际开源备用（某些数据源可能会将台湾单独列出，不推荐优先使用，仅作技术备选）
                "https://raw.githubusercontent.com/datasets/geo-boundaries-world-110m/master/countries.geojson",
                "https://raw.githubusercontent.com/datasets/geo-countries/master/data/countries.geojson",
                "https://raw.githubusercontent.com/holtzy/D3-graph-gallery/master/DATA/world.geojson",
                "https://datahub.io/core/geo-countries/r/countries.geojson",
                "https://raw.githubusercontent.com/johan/world.geo.json/master/countries.geo.json",
                "https://thematicmapping.org/downloads/world_borders.geojson",  # Old, but as extra fallback
                "https://github.com/datasets/geo-admin1-us/raw/master/data/admin1-states.geojson",  # US states, as fallback
            ]
    
            
            # 国家名称的多种可能匹配方式
            name_variants = {
                "Netherlands": ["Netherlands", "The Netherlands", "NLD", "Holland"],
                "China": ["China", "People's Republic of China", "CHN", "PRC"],
                "Japan": ["Japan", "JPN"],
                "United States of America": ["United States of America", "United States", "USA", "US"]
            }
            
            # 台湾的各种可能名称（用于合并到中国）
            taiwan_variants = ["Taiwan", "Taiwan, Province of China", "Republic of China", "TWN", "TW"]
            
            country_variants = name_variants.get(country_name_en, [country_name_en])
            
            for url in geojson_urls:
                try:
                    response = requests.get(url, timeout=15)
                    if response.status_code == 200:
                        world_geojson = response.json()
                        # 在 GeoJSON 中查找指定国家
                        main_feature = None
                        taiwan_feature = None
                        
                        for feature in world_geojson.get('features', []):
                            props = feature.get('properties', {})
                            
                            # 查找主国家
                            if main_feature is None:
                                for variant in country_variants:
                                    if (props.get('NAME') == variant or 
                                        props.get('NAME_LONG') == variant or
                                        props.get('NAME_EN') == variant or
                                        props.get('name') == variant or
                                        props.get('NAME_ISO') == variant or
                                        props.get('ISO_A3') == variant or
                                        props.get('ADMIN') == variant or
                                        props.get('admin') == variant):
                                        main_feature = feature
                                        break
                            
                            # 如果是中国，同时查找台湾
                            if country_name_en == "China" and taiwan_feature is None:
                                for variant in taiwan_variants:
                                    if (props.get('NAME') == variant or 
                                        props.get('NAME_LONG') == variant or
                                        props.get('NAME_EN') == variant or
                                        props.get('name') == variant or
                                        props.get('NAME_ISO') == variant or
                                        props.get('ISO_A3') == variant or
                                        props.get('ADMIN') == variant or
                                        props.get('admin') == variant):
                                        taiwan_feature = feature
                                        break
                        
                        # 如果找到主国家，尝试合并台湾
                        if main_feature:
                            if country_name_en == "China" and taiwan_feature:
                                # 合并中国和台湾的几何数据
                                import copy
                                merged_feature = copy.deepcopy(main_feature)
                                main_geom = merged_feature.get('geometry', {})
                                taiwan_geom = taiwan_feature.get('geometry', {})
                                
                                # 如果主几何是Polygon，转换为MultiPolygon
                                if main_geom.get('type') == 'Polygon':
                                    main_geom['type'] = 'MultiPolygon'
                                    main_geom['coordinates'] = [main_geom['coordinates']]
                                
                                # 添加台湾的几何到MultiPolygon中
                                if main_geom.get('type') == 'MultiPolygon':
                                    if taiwan_geom.get('type') == 'Polygon':
                                        main_geom['coordinates'].append(taiwan_geom['coordinates'])
                                    elif taiwan_geom.get('type') == 'MultiPolygon':
                                        main_geom['coordinates'].extend(taiwan_geom['coordinates'])
                                
                                return merged_feature
                            else:
                                return main_feature
                except Exception as e:
                    continue  # 尝试下一个 URL
            
        except Exception as e:
            print(f"加载 {country_name_en} 边界数据失败: {e}")
        
        return None
    
    # 为每个有风险的国家添加高亮层
    for item in gdp_list:
        country_name = item['location']
        if country_name in country_name_mapping:
            country_name_en = country_name_mapping[country_name]
            # 确保 gdp_value 是数字类型
            gdp_value = float(item['gdp']) if isinstance(item['gdp'], (int, float, str)) else 0
            
            # 根据风险值设置颜色和透明度（与图例保持一致）
            # 图例定义：高风险（GDP>10%）、中风险（5%<GDP≤10%）、低风险（GDP≤5%）
            if gdp_value > 10:
                highlight_color = "#e67e22"  # 橙色 - 高风险（GDP>10%）
                fill_opacity = 0.15  # 填充透明度，保持较低以不遮挡地图
                border_opacity = 1.0  # 边框完全不透明，与图例一致
                weight = 3
            elif gdp_value > 5:
                highlight_color = "#f1c40f"  # 黄色 - 中风险（5%<GDP≤10%）
                fill_opacity = 0.12
                border_opacity = 1.0
                weight = 2.5
            else:
                highlight_color = "#3498db"  # 蓝色 - 低风险（GDP≤5%）
                fill_opacity = 0.1
                border_opacity = 1.0
                weight = 2
            
            # 调试信息：打印国家名称和对应的颜色
            # print(f"国家: {country_name}, GDP: {gdp_value}%, 颜色: {highlight_color}")
            
            # 加载国家边界 GeoJSON 数据
            country_feature = load_country_geojson(country_name_en)
            
            # 使用闭包捕获颜色值，确保样式函数使用正确的颜色
            def make_style_function(color, w, fill_op, border_op):
                def style_function(feature):
                    return {
                        'fillColor': color,
                        'color': color,  # 边框颜色与填充颜色一致，与图例对齐
                        'weight': w,
                        'fillOpacity': fill_op,
                        'opacity': border_op  # 边框完全不透明，确保颜色与图例一致
                    }
                return style_function
            
            def make_highlight_function(color, w, fill_op, border_op):
                def highlight_function(feature):
                    return {
                        'fillColor': color,
                        'color': color,  # 保持边框颜色不变
                        'weight': w,
                        'fillOpacity': fill_op,
                        'opacity': border_op  # 保持边框完全不透明
                    }
                return highlight_function
            
            # 创建样式函数，确保使用正确的颜色值
            style_func = make_style_function(highlight_color, weight, fill_opacity, border_opacity)
            highlight_func = make_highlight_function(highlight_color, weight, fill_opacity, border_opacity)
            
            # 只有在成功加载国家边界数据时才添加高亮
            if country_feature:
                # 创建 GeoJson 图层（不显示点击弹窗和边框高亮，只保留悬停提示）
                geojson_layer = folium.GeoJson(
                    country_feature,
                    style_function=style_func,
                    highlight_function=highlight_func,
                    tooltip=folium.Tooltip(
                        f"<div style='font-family: Segoe UI;'><strong>{country_name}</strong><br>GDP风险: {gdp_value}%</div>",
                        style="font-family: Segoe UI;"
                    )
                )
                geojson_layer.add_to(m)
                
                # 如果是中国，额外确保台湾也被高亮（备用方案：如果合并失败，单独添加台湾）
                if country_name_en == "China":
                    # 检查加载的feature是否包含台湾（通过检查几何范围是否包含台湾的大致位置）
                    # 台湾大致位置：纬度23-25，经度119-122
                    geom = country_feature.get('geometry', {})
                    coords = geom.get('coordinates', [])
                    
                    # 简单检查：如果坐标范围不包含台湾区域，则单独加载台湾
                    has_taiwan = False
                    if geom.get('type') in ['Polygon', 'MultiPolygon']:
                        def check_coords_in_taiwan_range(coords_list):
                            """递归检查坐标是否在台湾范围内"""
                            for coord in coords_list:
                                if isinstance(coord[0], (int, float)):
                                    # 这是一个坐标点 [lon, lat]
                                    if 119 <= coord[0] <= 122 and 23 <= coord[1] <= 25:
                                        return True
                                else:
                                    # 这是嵌套的坐标列表
                                    if check_coords_in_taiwan_range(coord):
                                        return True
                            return False
                        
                        if geom.get('type') == 'Polygon':
                            has_taiwan = check_coords_in_taiwan_range(coords)
                        elif geom.get('type') == 'MultiPolygon':
                            for polygon in coords:
                                if check_coords_in_taiwan_range(polygon):
                                    has_taiwan = True
                                    break
                    
                    # 如果没有检测到台湾，单独加载并添加台湾高亮
                    if not has_taiwan:
                        # 单独加载台湾边界
                        taiwan_variants = ["Taiwan", "Taiwan, Province of China", "Republic of China", "TWN", "TW"]
                        geojson_urls = [
                            "https://geo.datav.aliyun.com/areas_v3/bound/geojson?code=all",
                            "https://geo.datav.aliyun.com/areas/bound/geojson?code=all",
                            "https://raw.githubusercontent.com/datasets/geo-boundaries-world-110m/master/countries.geojson",
                            "https://raw.githubusercontent.com/datasets/geo-countries/master/data/countries.geojson",
                        ]
                        
                        taiwan_feature = None
                        for url in geojson_urls:
                            try:
                                response = requests.get(url, timeout=15)
                                if response.status_code == 200:
                                    world_geojson = response.json()
                                    for feature in world_geojson.get('features', []):
                                        props = feature.get('properties', {})
                                        for variant in taiwan_variants:
                                            if (props.get('NAME') == variant or 
                                                props.get('NAME_LONG') == variant or
                                                props.get('NAME_EN') == variant or
                                                props.get('name') == variant or
                                                props.get('NAME_ISO') == variant or
                                                props.get('ISO_A3') == variant or
                                                props.get('ADMIN') == variant or
                                                props.get('admin') == variant):
                                                taiwan_feature = feature
                                                break
                                        if taiwan_feature:
                                            break
                                if taiwan_feature:
                                    break
                            except Exception:
                                continue
                        
                        # 如果找到台湾边界，添加高亮层（使用与中国相同的样式）
                        if taiwan_feature:
                            taiwan_layer = folium.GeoJson(
                                taiwan_feature,
                                style_function=style_func,
                                highlight_function=highlight_func,
                                tooltip=folium.Tooltip(
                                    f"<div style='font-family: Segoe UI;'><strong>{country_name}</strong><br>GDP风险: {gdp_value}%</div>",
                                    style="font-family: Segoe UI;"
                                )
                            )
                            taiwan_layer.add_to(m)
                            print(f"已为中国添加台湾地区高亮显示（使用相同颜色和样式）")
            else:
                print(f"警告: 无法加载 {country_name} ({country_name_en}) 的边界数据")
            

    # 1. 渲染地缘政治风险圆圈 (GDP) - 根据风险值使用不同颜色
    for item in gdp_list:
        # 高风险（>10%）用橙色，低风险用蓝色
        circle_color = "#e67e22" if item['gdp'] > 10 else "#3498db"
        risk_level = "高" if item['gdp'] > 10 else "中" if item['gdp'] > 5 else "低"
        
        tooltip_text = f"<div style='font-family: Segoe UI;'><strong>{item['location']}</strong><br>GDP风险: {item['gdp']}% ({risk_level}风险)</div>"
        
        # 构建专业的 popup 内容
        popup_content = f'''
        <div style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; min-width: 250px;">
            <div style="background: linear-gradient(135deg, {circle_color} 0%, {circle_color}dd 100%); 
                        color: white; padding: 12px; border-radius: 6px 6px 0 0; margin: -10px -10px 10px -10px;">
                <h3 style="margin: 0; font-size: 16px; font-weight: 600;">{item['location']}</h3>
                <div style="font-size: 12px; margin-top: 4px; opacity: 0.9;">地缘政治风险 (GDP)</div>
            </div>
            <div style="padding: 10px 0;">
                <div style="display: flex; justify-content: space-between; margin-bottom: 10px; padding: 8px; background: #f8f9fa; border-radius: 4px;">
                    <span style="color: #34495e; font-weight: 500;">风险值:</span>
                    <span style="color: {circle_color}; font-size: 18px; font-weight: bold;">{item['gdp']}%</span>
                </div>
                <div style="display: flex; justify-content: space-between; margin-bottom: 10px; padding: 8px; background: #f8f9fa; border-radius: 4px;">
                    <span style="color: #34495e; font-weight: 500;">风险等级:</span>
                    <span style="color: {circle_color}; font-weight: 600;">{risk_level}风险</span>
                </div>
        '''
        if 'key_risk' in item and item['key_risk']:
            popup_content += f'''
                <div style="margin-top: 10px; padding: 10px; background: #fff3cd; border-left: 3px solid #ffc107; border-radius: 4px;">
                    <div style="font-size: 11px; color: #856404; font-weight: 600; margin-bottom: 4px;">核心风险点:</div>
                    <div style="font-size: 12px; color: #856404; line-height: 1.5;">{item['key_risk']}</div>
                </div>
            '''
        elif 'info' in item and item['info']:
            popup_content += f'''
                <div style="margin-top: 10px; padding: 10px; background: #fff3cd; border-left: 3px solid #ffc107; border-radius: 4px;">
                    <div style="font-size: 11px; color: #856404; font-weight: 600; margin-bottom: 4px;">风险说明:</div>
                    <div style="font-size: 12px; color: #856404; line-height: 1.5;">{item['info']}</div>
                </div>
            '''
        popup_content += '''
            </div>
        </div>
        '''
        
        folium.Circle(
            location=item['coord'],
            radius=item['gdp'] * 50000,  # 按比例放大半径
            color=circle_color,
            fill=True,
            fill_opacity=0.4,
            weight=2,
            tooltip=folium.Tooltip(tooltip_text, style="font-family: Segoe UI;"),
            popup=folium.Popup(popup_content, max_width=300)
        ).add_to(m)

    # 2. 渲染自然灾变节点 (NDP) - 使用改进的图标和弹窗
    # 根据灾种类型选择不同图标
    hazard_icons = {
        "地震": ("exclamation-triangle", "#e74c3c"),  # 红色
        "台风": ("wind", "#e74c3c"),  # 蓝色，风图标
        "洪水": ("tint", "#e74c3c"),  # 蓝色，水滴图标
    }
    
    for item in ndp_list:
        hazard = item['hazard']
        city = item.get('city', '')
        hazard_name = f"{hazard}风险" if city else f"{hazard}风险 ({city})"
        
        icon_name, icon_color = hazard_icons.get(hazard, ("info-sign", "#e74c3c"))
        
        tooltip_text = f'''
        <div style='font-family: Segoe UI;'>
            <strong>{hazard}风险</strong><br>
            {city}<br>
            概率: {item['prob']}%
        </div>
        '''
        
        # 构建专业的 popup 内容
        popup_content = f'''
        <div style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; min-width: 250px;">
            <div style="background: linear-gradient(135deg, {icon_color} 0%, {icon_color}dd 100%); 
                        color: white; padding: 12px; border-radius: 6px 6px 0 0; margin: -10px -10px 10px -10px;">
                <h3 style="margin: 0; font-size: 16px; font-weight: 600;">{hazard}风险</h3>
                <div style="font-size: 12px; margin-top: 4px; opacity: 0.9;">自然灾害风险 (NDP)</div>
            </div>
            <div style="padding: 10px 0;">
                <div style="margin-bottom: 10px; padding: 8px; background: #f8f9fa; border-radius: 4px;">
                    <div style="color: #34495e; font-weight: 500; margin-bottom: 4px;">区域位置:</div>
                    <div style="color: #2c3e50; font-size: 14px;">{city}</div>
                </div>
                <div style="display: flex; justify-content: space-between; margin-bottom: 10px; padding: 8px; background: #f8f9fa; border-radius: 4px;">
                    <span style="color: #34495e; font-weight: 500;">中断概率:</span>
                    <span style="color: {icon_color}; font-size: 18px; font-weight: bold;">{item['prob']}%</span>
                </div>
                <div style="display: flex; justify-content: space-between; margin-bottom: 10px; padding: 8px; background: #f8f9fa; border-radius: 4px;">
                    <span style="color: #34495e; font-weight: 500;">贡献度:</span>
                    <span style="color: #e67e22; font-size: 16px; font-weight: bold;">{item['contrib']}</span>
                </div>
                <div style="margin-top: 10px; padding: 8px; background: #e8f5e9; border-left: 3px solid #4caf50; border-radius: 4px;">
                    <div style="font-size: 11px; color: #2e7d32; font-weight: 600; margin-bottom: 4px;">风险说明:</div>
                    <div style="font-size: 12px; color: #2e7d32; line-height: 1.5;">
                        未来12个月内因{hazard}导致供应链中断≥24小时的概率
                    </div>
                </div>
            </div>
        </div>
        '''
        
        folium.Marker(
            location=item['coord'],
            icon=folium.Icon(color=hex_to_folium_color(icon_color), icon=icon_name, prefix='fa'),
            tooltip=folium.Tooltip(tooltip_text, style="font-family: Segoe UI;"),
            popup=folium.Popup(popup_content, max_width=300)
        ).add_to(m)

    # 3. 添加专业美观的风险概览面板
    risk_color = get_risk_color(overall_risk)
    
    # 构建置信区间显示
    confidence_text = ""
    if ndp_confidence_interval:
        confidence_text = f"<div style='margin-top:4px;'><small style='color:#7f8c8d; font-size:11px;'>95%置信区间: [{ndp_confidence_interval[0]:.1f}%, {ndp_confidence_interval[1]:.1f}%]</small></div>"
    
    # 构建GDP数据表格HTML
    gdp_table_rows = ""
    for item in sorted(gdp_list, key=lambda x: x['gdp'], reverse=True):
        risk_level = "高" if item['gdp'] > 10 else "中" if item['gdp'] > 5 else "低"
        row_color = "#e74c3c" if item['gdp'] > 10 else "#f1c40f" if item['gdp'] > 5 else "#27ae60"
        gdp_table_rows += f'''
        <tr style="border-bottom: 1px solid #ecf0f1;">
            <td style="padding: 6px 8px;">{item['location']}</td>
            <td style="padding: 6px 8px; text-align: center;"><span style="color:{row_color}; font-weight: bold;">{item['gdp']}%</span></td>
            <td style="padding: 6px 8px; text-align: center;"><span style="color:{row_color};">{risk_level}</span></td>
        </tr>
        '''
    
    # 构建NDP数据表格HTML
    ndp_table_rows = ""
    for item in sorted(ndp_list, key=lambda x: x['prob'], reverse=True):
        ndp_table_rows += f'''
        <tr style="border-bottom: 1px solid #ecf0f1;">
            <td style="padding: 6px 8px;">{item['hazard']}</td>
            <td style="padding: 6px 8px;">{item['city']}</td>
            <td style="padding: 6px 8px; text-align: center;"><span style="color:#e74c3c; font-weight: bold;">{item['prob']}%</span></td>
            <td style="padding: 6px 8px; text-align: center;">{item['contrib']}</td>
        </tr>
        '''
    
    risk_summary_html = f'''
        <div id="risk-panel" style="position: fixed; 
        bottom: 20px; left: 20px; width: 380px; max-height: 85vh; overflow-y: auto;
        background: linear-gradient(135deg, #ffffff 0%, #f8f9fa 100%); 
        border: 2px solid {risk_color}; z-index:9999; font-size:13px;
        padding: 20px; border-radius: 12px; box-shadow: 0 4px 20px rgba(0,0,0,0.15);
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        transition: all 0.3s ease;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px;">
            <h3 style="margin: 0; font-size: 18px; color: #2c3e50; font-weight: 600;">供应链风险监控面板</h3>
            <button onclick="togglePanel()" style="background: {risk_color}; color: white; border: none; 
            border-radius: 4px; padding: 4px 10px; cursor: pointer; font-size: 11px;">折叠</button>
        </div>
        
        <div id="panel-content">
        <div style="background: {risk_color}15; padding: 12px; border-radius: 8px; margin-bottom: 15px; border-left: 4px solid {risk_color};">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <span style="color: #34495e; font-weight: 500;">整体风险评级{create_info_icon("overall_risk")}</span>
                <span style="color: {risk_color}; font-size: 20px; font-weight: bold;">{overall_risk}</span>
            </div>
        </div>
        
        <div style="margin-bottom: 15px;">
            <div style="display: flex; justify-content: space-between; margin-bottom: 8px;">
                <span style="color: #34495e; font-weight: 500;">综合GDP概率</span>
                <span style="color: #e67e22; font-size: 16px; font-weight: bold;">{avg_gdp:.1f}%</span>
            </div>
            <div style="display: flex; justify-content: space-between; margin-bottom: 8px;">
                <span style="color: #34495e; font-weight: 500;">综合NDP概率</span>
                <span style="color: #e74c3c; font-size: 16px; font-weight: bold;">{total_ndp:.1f}%</span>
            </div>
            {confidence_text}
        </div>
        
        <div style="margin-bottom: 15px;">
            <h4 style="margin: 0 0 10px 0; font-size: 14px; color: #2c3e50; font-weight: 600;">地缘政治风险 (GDP){create_info_icon("gdp")}</h4>
            <table style="width: 100%; border-collapse: collapse; font-size: 12px;">
                <thead>
                    <tr style="background: #ecf0f1; border-bottom: 2px solid #bdc3c7;">
                        <th style="padding: 8px; text-align: left;">地区</th>
                        <th style="padding: 8px; text-align: center;">风险值{create_info_icon("risk_value")}</th>
                        <th style="padding: 8px; text-align: center;">等级{create_info_icon("risk_level")}</th>
                    </tr>
                </thead>
                <tbody>
                    {gdp_table_rows}
                </tbody>
            </table>
        </div>
        
        <div style="margin-bottom: 15px;">
            <h4 style="margin: 0 0 10px 0; font-size: 14px; color: #2c3e50; font-weight: 600;">自然灾害风险 (NDP){create_info_icon("ndp")}</h4>
            <table style="width: 100%; border-collapse: collapse; font-size: 12px;">
                <thead>
                    <tr style="background: #ecf0f1; border-bottom: 2px solid #bdc3c7;">
                        <th style="padding: 8px; text-align: left;">灾种</th>
                        <th style="padding: 8px; text-align: left;">区域</th>
                        <th style="padding: 8px; text-align: center;">概率{create_info_icon("probability")}</th>
                        <th style="padding: 8px; text-align: center;">贡献度{create_info_icon("contribution")}</th>
                    </tr>
                </thead>
                <tbody>
                    {ndp_table_rows}
                </tbody>
            </table>
        </div>
        
        <div style="background: #ecf0f1; padding: 10px; border-radius: 6px; font-size: 11px; color: #7f8c8d;">
            <strong>说明：</strong>国家区域高亮显示风险等级，圆圈大小代表地缘政治风险值，点击标记查看详细信息
        </div>
        </div>
        
        <script>
        function togglePanel() {{
            var content = document.getElementById('panel-content');
            var btn = event.target;
            if (content.style.display === 'none') {{
                content.style.display = 'block';
                btn.textContent = '折叠';
            }} else {{
                content.style.display = 'none';
                btn.textContent = '展开';
            }}
        }}
        </script>
        </div>
    '''
    m.get_root().html.add_child(folium.Element(risk_summary_html))
    
    # 4. 添加专业图例和筛选功能
    legend_html = '''
        <div style="position: fixed; 
        top: 20px; right: 20px; width: 240px; 
        background: linear-gradient(135deg, #ffffff 0%, #f8f9fa 100%); 
        border: 2px solid #bdc3c7; z-index:9999; font-size:12px;
        padding: 15px; border-radius: 10px; box-shadow: 0 4px 15px rgba(0,0,0,0.1);
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;">
        <h4 style="margin: 0 0 12px 0; font-size: 14px; color: #2c3e50; font-weight: 600; border-bottom: 2px solid #ecf0f1; padding-bottom: 8px;">图例与筛选</h4>
        
        <div style="margin-bottom: 12px;">
            <div style="margin-bottom: 8px; font-size: 11px; color: #7f8c8d; font-weight: 600;">国家风险区域：</div>
            <div style="margin: 6px 0; display: flex; align-items: center;">
                <span style="display:inline-block; width:20px; height:12px; background:#e67e22; border: 2px solid #e67e22; margin-right:8px; opacity: 0.6;"></span>
                <span style="color: #34495e; font-size: 11px;">高风险国家（GDP&gt;10%）</span>
            </div>
            <div style="margin: 6px 0; display: flex; align-items: center;">
                <span style="display:inline-block; width:20px; height:12px; background:#f1c40f; border: 2px solid #f1c40f; margin-right:8px; opacity: 0.6;"></span>
                <span style="color: #34495e; font-size: 11px;">中风险国家（5%&lt;GDP≤10%）</span>
            </div>
            <div style="margin: 6px 0; display: flex; align-items: center;">
                <span style="display:inline-block; width:20px; height:12px; background:#3498db; border: 2px solid #3498db; margin-right:8px; opacity: 0.6;"></span>
                <span style="color: #34495e; font-size: 11px;">低风险国家（GDP&le;5%）</span>
            </div>
        </div>
        
        <hr style="margin: 10px 0; border: none; border-top: 1px solid #ecf0f1;">
        
        <div style="margin-bottom: 12px;">
            <div style="margin-bottom: 8px; font-size: 11px; color: #7f8c8d; font-weight: 600;">风险标记：</div>
            <div style="margin: 6px 0; display: flex; align-items: center;">
                <span style="display:inline-block; width:16px; height:16px; background:#e67e22; border-radius:50%; margin-right:8px; border: 2px solid #fff; box-shadow: 0 0 0 1px #e67e22;"></span>
                <span style="color: #34495e; font-size: 11px;">GDP风险 >10% (高)</span>
            </div>
            <div style="margin: 6px 0; display: flex; align-items: center;">
                <span style="display:inline-block; width:16px; height:16px; background:#3498db; border-radius:50%; margin-right:8px; border: 2px solid #fff; box-shadow: 0 0 0 1px #3498db;"></span>
                <span style="color: #34495e; font-size: 11px;">GDP风险 ≤10% (中低)</span>
            </div>
            <div style="margin: 6px 0; display: flex; align-items: center;">
                <span style="display:inline-block; width:16px; height:16px; background:#e74c3c; border-radius:50%; margin-right:8px; border: 2px solid #fff; box-shadow: 0 0 0 1px #e74c3c;"></span>
                <span style="color: #34495e; font-size: 11px;">自然灾害风险</span>
            </div>

        </div>
        
        <hr style="margin: 10px 0; border: none; border-top: 1px solid #ecf0f1;">
        
        
        <hr style="margin: 10px 0; border: none; border-top: 1px solid #ecf0f1;">
        
        <div style="font-size: 10px; color: #7f8c8d; line-height: 1.5;">
            <strong>提示：</strong>点击地图上的标记或圆圈查看详细信息
        </div>
        </div>
    '''
    m.get_root().html.add_child(folium.Element(legend_html))
    
    # 添加 JavaScript 代码禁用 GeoJson 图层的点击边框高亮
    disable_click_border_js = '''
    <script>
    (function() {
        // 等待地图加载完成后执行
        setTimeout(function() {
            // 禁用所有 GeoJson 路径的点击边框高亮
            var paths = document.querySelectorAll('path.leaflet-interactive');
            paths.forEach(function(path) {
                // 移除点击事件
                path.style.pointerEvents = 'auto';
                path.style.cursor = 'default';
                
                // 禁用焦点样式
                path.addEventListener('click', function(e) {
                    e.stopPropagation();
                    // 移除可能的高亮类
                    this.classList.remove('leaflet-clickable');
                }, true);
                
                // 禁用鼠标按下时的样式变化
                path.addEventListener('mousedown', function(e) {
                    e.stopPropagation();
                }, true);
            });
            
            // 监听地图上的点击事件，移除 GeoJson 图层的焦点
            var mapContainer = document.querySelector('.folium-map');
            if (mapContainer) {
                mapContainer.addEventListener('click', function(e) {
                    // 移除所有路径的焦点状态
                    paths.forEach(function(path) {
                        path.blur();
                        path.style.outline = 'none';
                        path.style.stroke = path.getAttribute('stroke') || '';
                    });
                });
            }
        }, 500);
    })();
    </script>
    '''
    m.get_root().html.add_child(folium.Element(disable_click_border_js))
    
    # 数据验证
    if not gdp_list and not ndp_list:
        print("警告: 未提取到任何风险数据，地图可能为空")
    
    # 保存地图
    try:
        m.save(output_html)
        print(f"成功！已基于报告生成动态风险地图: {output_html}")
        print(f"  - GDP风险点: {len(gdp_list)}个")
        print(f"  - NDP风险点: {len(ndp_list)}个")
        print(f"  - 整体风险等级: {overall_risk}")
        if gdp_overall:
            print(f"  - 综合GDP概率: {gdp_overall:.1f}%")
        if ndp_overall:
            print(f"  - 综合NDP概率: {ndp_overall:.1f}%")
        return True
    except Exception as e:
        print(f"保存地图文件失败: {e}")
        return False

if __name__ == "__main__":
    generate_map("research_assessment_manager_report.md", "honda_risk_viz.html", use_llm=True, use_geocoding=True)