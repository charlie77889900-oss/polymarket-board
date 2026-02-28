import requests
import json
import ast
from datetime import datetime, timezone
import streamlit as st

# ================= 页面配置 =================
st.set_page_config(
    page_title="Polymarket | 终极量化看板",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 注入自定义 CSS
st.markdown("""
<style>
.market-card {
    background-color: #1E2026; 
    border-radius: 12px; 
    padding: 16px; 
    margin-bottom: 20px; 
    border: 1px solid #333; 
    height: 100%;
    transition: all 0.2s ease-in-out;
}
.market-card:hover {
    border-color: #555;
    transform: translateY(-3px);
    box-shadow: 0 4px 12px rgba(0,0,0,0.3);
}
</style>
""", unsafe_allow_html=True)

# ================= 配置、映射与辅助函数 =================
API_URL = "https://gamma-api.polymarket.com/markets"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

CATEGORY_MAPPING = {
    "🏛️ 政治 (Politics)":["politics", "elections", "us politics", "trump", "biden", "president", "harris", "senate"],
    "🪙 加密货币 (Crypto)":["crypto", "bitcoin", "ethereum", "solana", "btc", "eth", "defi"],
    "⚽ 体育 (Sports)":["sports", "soccer", "basketball", "nfl", "nba", "tennis", "premier league", "champions"],
    "🍿 流行文化 (Pop Culture)":["pop culture", "entertainment", "movies", "music", "oscars", "grammy", "box office"],
    "💼 商业与经济 (Business/Econ)":["business", "economics", "finance", "fed", "interest rate", "market", "acquisition"],
    "🔬 科学与科技 (Science/Tech)":["science", "technology", "space", "ai", "openai", "spacex", "gpt", "musk"]
}

def parse_list_field(field_data):
    if isinstance(field_data, list):
        return field_data
    if isinstance(field_data, str):
        try:
            return json.loads(field_data)
        except:
            try:
                return ast.literal_eval(field_data)
            except:
                return[]
    return[]

def format_volume(volume):
    if volume >= 1_000_000_000:
        return f"${volume / 1_000_000_000:.2f}B"
    elif volume >= 1_000_000:
        return f"${volume / 1_000_000:.1f}M"
    elif volume >= 1_000:
        return f"${volume / 1_000:.1f}K"
    else:
        return f"${volume:.0f}"

# ================= 数据抓取逻辑 =================
@st.cache_data(ttl=60)
def fetch_filtered_markets(target_count=5, threshold=0.90, min_volume=1.0, allowed_keywords=None, order_by="volume"):
    markets =[]
    limit = 100  
    offset = 0
    max_pages = 30 
    
    now_utc = datetime.now(timezone.utc)
    
    for page in range(max_pages):
        try:
            # 动态改变排序参数：createdAt(最新) 还是 volume(交易量最热)
            params = {
                "active": "true",
                "closed": "false",
                "order": order_by,  
                "ascending": "false", 
                "limit": limit,
                "offset": offset
            }
            response = requests.get(API_URL, params=params, headers=HEADERS)
            response.raise_for_status()
            data = response.json()
            
            if not data:
                break 
                
            for item in data:
                if item.get("closed") is True or item.get("active") is False:
                    continue
                
                end_date_str = item.get("endDate")
                if end_date_str:
                    try:
                        end_date = datetime.fromisoformat(end_date_str.replace('Z', '+00:00'))
                        if end_date < now_utc:
                            continue
                    except Exception:
                        pass
                
                volume = float(item.get("volume") or 0)
                if volume < min_volume:
                    continue
                
                if allowed_keywords:
                    question_lower = item.get("question", "").lower()
                    raw_tags = parse_list_field(item.get("tags"))
                    
                    parsed_tags =[]
                    for t in raw_tags:
                        if isinstance(t, dict):
                            parsed_tags.append(str(t.get("label", "")).lower())
                        else:
                            parsed_tags.append(str(t).lower())
                            
                    matched = False
                    for kw in allowed_keywords:
                        if any(kw in pt for pt in parsed_tags) or (kw in question_lower):
                            matched = True
                            break
                    if not matched:
                        continue

                outcomes = parse_list_field(item.get("outcomes"))
                prices = parse_list_field(item.get("outcomePrices"))
                
                if not outcomes or not prices or len(outcomes) != len(prices):
                    continue
                
                options =[]
                has_high_prob = False
                for outcome_label, price_str in zip(outcomes, prices):
                    try:
                        price = float(price_str)
                    except:
                        price = 0.0
                    
                    if price >= threshold:
                        has_high_prob = True
                        
                    options.append({"label": outcome_label, "price": price})
                
                if has_high_prob:
                    image = item.get("image") or "https://polymarket.com/favicon.ico"
                    slug = item.get("slug") or ""
                    market_url = f"https://polymarket.com/event/{slug}" if slug else "https://polymarket.com/"
                    
                    options = sorted([o for o in options if o['price'] > 0.001], key=lambda x: x['price'], reverse=True)
                    
                    markets.append({
                        "question": item.get("question", "N/A"),
                        "image": image,
                        "volume_str": format_volume(volume),
                        "options": options,
                        "url": market_url
                    })
                    
                    if len(markets) >= target_count:
                        return markets
            
            offset += limit
            
        except Exception as e:
            st.error(f"第 {page+1} 页抓取失败: {e}")
            break
            
    return markets

# ================= 前端渲染 =================
def render_market_card(market, threshold_percent):
    top_options = market['options'][:3]
    options_html = ""
    
    for opt in top_options:
        prob_percent = int(opt['price'] * 100)
        
        if prob_percent >= threshold_percent:
            icon = "🔥 "
            bar_color = "#00C853"      
            bg_color = "#00C85330"     
            text_color = "#00C853"
        else:
            icon = ""
            bar_color = "#2D2DF2"      
            bg_color = "#2D2DF240"
            text_color = "#EFEFEF"

        options_html += f"""
<div style="display: flex; justify-content: space-between; font-size: 14px; margin-top: 8px; color: #ddd;">
<span style="font-weight: 500;">{icon}{opt['label']}</span>
<span style="font-weight: bold; color: {text_color};">{prob_percent}%</span>
</div>
<div style="background-color: {bg_color}; width: 100%; height: 6px; border-radius: 4px; margin-top: 4px;">
<div style="background-color: {bar_color}; width: {prob_percent}%; height: 100%; border-radius: 4px;"></div>
</div>
"""

    card_html = f"""
<a href="{market['url']}" target="_blank" style="text-decoration: none; color: inherit; display: block; height: 100%;">
<div class="market-card">
<div style="display: flex; align-items: flex-start; gap: 12px; margin-bottom: 12px;">
<img src="{market['image']}" style="width: 40px; height: 40px; border-radius: 50%; object-fit: cover;">
<div>
<div style="color: #FFFFFF; font-size: 16px; font-weight: 600; line-height: 1.3;">{market['question']}</div>
<div style="color: #8E929B; font-size: 12px; margin-top: 4px;">Vol: {market['volume_str']}</div>
</div>
</div>
<div style="margin-top: 16px;">
{options_html}
</div>
</div>
</a>
"""
    st.markdown(card_html, unsafe_allow_html=True)

def main():
    st.sidebar.header("⚙️ 抓取与过滤设置")
    
    # 【新增】核心排序切换开关
    sort_option = st.sidebar.radio(
        "📊 核心排序方式",
        options=["🔥 按交易量排序 (官网默认)", "⏱️ 按最新发布排序 (发现早期)"],
        index=0 # 默认选中第一个，即官网模式
    )
    api_order_by = "volume" if "交易量" in sort_option else "createdAt"

    st.sidebar.markdown("---")
    
    target_count_ui = st.sidebar.slider("📌 抓取条目数", min_value=1, max_value=100, value=6, step=1)
    threshold_ui = st.sidebar.slider("🎯 最小赔率阈值 (%)", min_value=0, max_value=100, value=90, step=1)
    
    # 交易量上限提升到 1,000,000（100万），为了更好地过滤巨型市场的门槛
    min_volume_ui = st.sidebar.slider("💰 最小交易量 ($)", min_value=1, max_value=1_000_000, value=1000, step=1000, format="%d")
    
    all_categories = list(CATEGORY_MAPPING.keys())
    selected_categories_ui = st.sidebar.multiselect(
        "🗂️ 关注的栏目", 
        options=all_categories, 
        default=all_categories 
    )
    
    st.sidebar.markdown("---")
    
    if st.sidebar.button("🔄 立即刷新/应用过滤", use_container_width=True):
        fetch_filtered_markets.clear()

    st.title(f"⚡ Polymarket 高级看板")
    
    mode_text = "最热大事件" if api_order_by == "volume" else "最新鲜发布"
    st.markdown(f"当前策略：抓取**{mode_text}** | **前 {target_count_ui} 条** | **赔率 ≥ {threshold_ui}%** | **交易量 ≥ ${min_volume_ui:,}**")
    
    allowed_keywords =[]
    for cat in selected_categories_ui:
        allowed_keywords.extend(CATEGORY_MAPPING[cat])
        
    if not selected_categories_ui:
        st.warning("⚠️ 请至少选择一个【栏目】！")
        return

    threshold_float = threshold_ui / 100.0

    with st.spinner(f"正在从 Polymarket 获取数据，请稍候..."):
        markets = fetch_filtered_markets(
            target_count=target_count_ui, 
            threshold=threshold_float, 
            min_volume=float(min_volume_ui),
            allowed_keywords=allowed_keywords,
            order_by=api_order_by  # 传入排序参数
        )
    
    if not markets:
        st.warning(f"🤷‍♂️ 暂无满足所有极端条件的数据。试试调低「赔率」或「交易量」。")
        return

    for i in range(0, len(markets), 3):
        cols = st.columns(3)
        for j in range(3):
            if i + j < len(markets):
                with cols[j]:
                    render_market_card(markets[i + j], threshold_ui)

if __name__ == "__main__":
    main()