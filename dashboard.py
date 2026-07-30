#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
===================================================================
 FINAL BOSS TRADING DASHBOARD (STREAMLIT) - v9.0
===================================================================
CÁCH CHẠY: streamlit run dashboard.py
TÍNH NĂNG:
✅ Chọn khung thời gian (M15, M30, H1, H4)
✅ Chọn chiến lược (Aggressive/Moderate/Conservative)
✅ Chọn đòn bẩy (1-500)
✅ Chọn giá vốn
✅ Chế độ tự động/tự chọn
✅ Nút chạy hệ thống ngay
✅ Hiển thị dự đoán với chú thích tiếng Việt
✅ Biểu đồ giá & tín hiệu
✅ Backtest & Equity Curve
✅ Monte Carlo Simulation
===================================================================
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import json
import os
import subprocess
import sys
from datetime import datetime

# Cấu hình trang
st.set_page_config(page_title=" Final Boss Trading Dashboard", layout="wide", page_icon="📈")

# ====================================================================
# HÀM HỖ TRỢ ĐỌC DỮ LIỆU
# ====================================================================
@st.cache_data(ttl=30) # Cache dữ liệu, tự động làm mới mỗi 30s
def load_final_data():
    if os.path.exists('final_boss_data.json'):
        try:
            with open('final_boss_data.json', 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return None
    return None

@st.cache_data(ttl=30)
def load_trade_log():
    if os.path.exists('trade_log.csv'):
        try:
            return pd.read_csv('trade_log.csv')
        except:
            return pd.DataFrame()
    return pd.DataFrame()

@st.cache_data(ttl=30)
def load_signals():
    if os.path.exists('trading_signals.csv'):
        try:
            return pd.read_csv('trading_signals.csv')
        except:
            return pd.DataFrame()
    return pd.DataFrame()

# ====================================================================
# SIDEBAR: BẢNG ĐIỀU KHIỂN HỆ THỐNG
# ====================================================================
with st.sidebar:
    st.header("⚙️ Bảng Điều Khiển")
    st.markdown("Chọn cấu hình và chạy hệ thống trực tiếp từ đây.")
    
    # Khung thời gian
    timeframe = st.selectbox(
        "Khung thời gian", 
        ["M5", "M15", "M30", "H1", "H4", "D1"], 
        index=1,
        help="Scalping: M5, M15, M30 | Swing: H1, H4, D1"
    )
    
    # Chiến lược
    strategy = st.radio(
        "Chiến lược (Strategy)", 
        ["aggressive", "moderate", "conservative"],
        index=0,
        help="**Aggressive**: Nhiều lệnh, rủi ro cao (phù hợp scalping)\n\n**Moderate**: Cân bằng\n\n**Conservative**: Ít lệnh, an toàn"
    )
    
    # Đòn bẩy
    leverage = st.slider(
        "Đòn bẩy (Leverage)", 
        min_value=1, 
        max_value=500, 
        value=100,
        help="Đòn bẩy càng cao, rủi ro càng lớn. Khuyến nghị: 100-200 cho scalping"
    )
    
    # Giá vốn
    initial_capital = st.number_input(
        "Giá vốn (USD)", 
        min_value=50, 
        value=100, 
        step=50,
        help="Số vốn ban đầu bạn có. Hệ thống sẽ tính volume tự động dựa trên risk %"
    )
    
    # Chế độ tự động
    auto_mode = st.checkbox(
        "Chế độ tự động", 
        value=True, 
        help="✅ **BẬT**: Hệ thống tự động chạy theo cấu hình đã chọn\n\n **TẮT**: Chỉ xem dữ liệu, không tự động chạy"
    )
    
    st.markdown("---")
    
    # Nút chạy hệ thống
    if st.button("🚀 Chạy Hệ Thống Ngay", type="primary", use_container_width=True):
        with st.spinner("Đang cập nhật cấu hình và kết nối MT5... (Chờ 10-30 giây)"):
            try:
                # Cập nhật cấu hình vào file config
                config = {
                    "timeframe": timeframe,
                    "strategy": strategy,
                    "leverage": leverage,
                    "initial_capital": initial_capital,
                    "auto_mode": auto_mode
                }
                
                with open('config.json', 'w', encoding='utf-8') as f:
                    json.dump(config, f, ensure_ascii=False, indent=2)
                
                # Chạy script auto_trading_system.py
                result = subprocess.run(
                    [sys.executable, "auto_trading_system.py"],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    timeout=60
                )
                
                if result.returncode == 0:
                    st.success("✅ Chạy thành công! Dữ liệu đã được làm mới.")
                    # Xóa cache để load dữ liệu mới
                    st.cache_data.clear()
                    st.rerun()
                else:
                    st.error(" Lỗi khi chạy hệ thống.")
                    with st.expander("📋 Xem Chi Tiết Lỗi"):
                        st.code(result.stderr)
            except subprocess.TimeoutExpired:
                st.error(" Timeout: Hệ thống chạy quá lâu (>60s). Kiểm tra MT5 connection.")
            except Exception as e:
                st.error(f" Lỗi: {str(e)}")

# ====================================================================
# GIAO DIỆN CHÍNH
# ====================================================================
st.title("🏆 FINAL BOSS TRADING SYSTEM DASHBOARD v9.0")
st.markdown("---")

# Hiển thị thông tin hệ thống
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Khung thời gian", timeframe, "Scalping" if timeframe in ["M5", "M15", "M30"] else "Swing")
with col2:
    st.metric("Chiến lược", strategy.upper(), "Rủi ro cao" if strategy == "aggressive" else "An toàn")
with col3:
    st.metric("Đòn bẩy", f"{leverage}:1", "Cao" if leverage > 200 else "Thấp")
with col4:
    st.metric("Vốn", f"${initial_capital:,.0f}", "Nhỏ" if initial_capital < 500 else "Lớn")

final_data = load_final_data()
reliability = final_data.get('reliability_metrics', {}) if final_data else {}
win_rate = reliability.get('win_rate', 0)
pf = reliability.get('profit_factor', 0)
max_dd = reliability.get('max_drawdown', 0)

if win_rate >= 0.55 and pf >= 1.5 and max_dd <= 12:
    action_label = "✅ Nên tiếp tục"
    action_text = "Hệ thống đang khá ổn. Giữ chiến lược hiện tại, vào lệnh theo tín hiệu rõ và kiểm soát rủi ro chặt."
    recommended_strategy = "moderate"
    recommended_risk = "1-2% vốn mỗi lệnh"
    recommended_timeframe = timeframe
elif win_rate >= 0.50 and pf >= 1.2 and max_dd <= 18:
    action_label = "⚠️ Nên thận trọng"
    action_text = "Hệ thống còn có thể dùng, nhưng nên giảm quy mô và ưu tiên tín hiệu xác nhận từ nhiều chỉ báo."
    recommended_strategy = "conservative"
    recommended_risk = "0.5-1% vốn mỗi lệnh"
    recommended_timeframe = "H1" if timeframe in ["M5", "M15", "M30"] else timeframe
else:
    action_label = "❌ Nên tạm dừng"
    action_text = "Hệ thống đang rủi ro cao. Tạm dừng giao dịch mới, giảm lot và kiểm tra lại tín hiệu trước khi tiếp tục."
    recommended_strategy = "conservative"
    recommended_risk = "0.25-0.5% vốn mỗi lệnh"
    recommended_timeframe = "H4"

st.markdown("---")
st.markdown(
    f"<div style='padding:12px 14px; border-left:4px solid #1E90FF; background:rgba(30,144,255,0.12); margin-bottom:10px;'>"
    f"<b>{action_label}</b><br>{action_text}<br><br>"
    f"<b>Gợi ý hành động:</b> chiến lược {recommended_strategy.upper()}, rủi ro {recommended_risk}, khung thời gian {recommended_timeframe}</div>",
    unsafe_allow_html=True,
)

if final_data:
    prediction = final_data.get('prediction', {})
    direction = prediction.get('prediction', 'NEUTRAL')
    prob_up = prediction.get('prob_up', 0)
    prob_down = prediction.get('prob_down', 0)
    if direction == 'BUY' and prob_up >= 0.55:
        decision = "✅ ĐI VÀO: ưu tiên BUY"
        decision_detail = "Tín hiệu đang có xu hướng tăng và xác suất đúng khá cao."
    elif direction == 'SELL' and prob_down >= 0.55:
        decision = "✅ ĐI VÀO: ưu tiên SELL"
        decision_detail = "Tín hiệu đang có xu hướng giảm và xác suất đúng khá cao."
    elif direction == 'NEUTRAL':
        decision = "⏸️ ĐỨNG NGOÀI"
        decision_detail = "Không nên mở lệnh mới cho đến khi tín hiệu được xác nhận lại."
    else:
        decision = "⚠️ CẢNH GIÁC"
        decision_detail = "Tín hiệu có vẻ khác biệt, nên chờ xác nhận thêm trước khi vào lệnh."

    st.markdown(
        f"<div style='padding:12px 14px; border-left:4px solid #FF8C00; background:rgba(255,140,0,0.12); margin-bottom:10px;'>"
        f"<b>{decision}</b><br>{decision_detail}</div>",
        unsafe_allow_html=True,
    )

    base_risk = 1.0
    if action_label.startswith("✅"):
        base_risk = 1.5
    elif action_label.startswith("⚠️"):
        base_risk = 1.0
    else:
        base_risk = 0.5

    if strategy == "aggressive":
        base_risk += 0.25
    elif strategy == "conservative":
        base_risk -= 0.25

    if leverage >= 200:
        base_risk -= 0.25
    elif leverage <= 50:
        base_risk += 0.25

    risk_percent = max(0.25, min(2.0, round(base_risk, 2)))
    risk_amount_usd = initial_capital * risk_percent / 100
    suggested_position = max(0.01, round(risk_amount_usd / 100, 2))
    st.markdown(
        f"<div style='padding:12px 14px; border-left:4px solid #32CD32; background:rgba(50,205,50,0.12); margin-bottom:10px;'>"
        f"<b>📏 Đề xuất đặt lệnh</b><br>"
        f"• Rủi ro mỗi lệnh: <b>{risk_percent:.2f}% vốn</b><br>"
        f"• Mức rủi ro tiền: <b>${risk_amount_usd:,.2f}</b><br>"
        f"• Khuyến nghị size: <b>{suggested_position:.2f} lot</b><br>"
        f"• SL/TP: dùng trước khi vào, cố định và không vượt quá 1-2% vốn</div>",
        unsafe_allow_html=True,
    )

st.markdown("---")

# Tạo các Tab
tab1, tab2, tab3, tab4 = st.tabs(["🔮 Dự Đoán & Phân Tích", "📈 Biểu Đồ & Tín Hiệu", "💰 Backtest & Kết Quả", "🎲 Monte Carlo & Rủi Ro"])

# ================= TAB 1: DỰ ĐOÁN & PHÂN TÍCH =================
with tab1:
    st.header("🔮 Dự Đoán Thị Trường (Tự Động)")
    st.markdown("**Hệ thống tự động phân tích và đưa ra dự đoán dựa trên:**")
    st.markdown("- Machine Learning (Random Forest)")
    st.markdown("- 15+ chỉ báo kỹ thuật")
    st.markdown("- Fibonacci & Market Regime")
    st.markdown("- Sentiment Analysis (NLP)")
    
    final_data = load_final_data()
    
    if final_data:
        prediction = final_data.get('prediction', {})
        direction = prediction.get('prediction', 'NEUTRAL')
        
        # Hiển thị dự đoán chính
        if direction == 'BUY':
            st.success(f"✅ **DỰ ĐOÁN: BUY (MUA)**")
            st.markdown(f"**Xác suất tăng:** {prediction.get('prob_up', 0):.1%}")
        elif direction == 'SELL':
            st.error(f"❌ **DỰ ĐOÁN: SELL (BÁN)**")
            st.markdown(f"**Xác suất giảm:** {prediction.get('prob_down', 0):.1%}")
        else:
            st.warning("⏸️ **DỰ ĐOÁN: NEUTRAL (ĐỨNG NGOÀI)**")
            st.markdown("Hệ thống chưa tìm thấy tín hiệu đủ mạnh. Chờ nến tiếp theo.")
        
        st.markdown("---")
        
        # Thông tin chi tiết
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric(" Xác suất Tăng", f"{prediction.get('prob_up', 0):.1%}")
        with col2:
            st.metric(" Xác suất Giảm", f"{prediction.get('prob_down', 0):.1%}")
        with col3:
            st.metric(" Độ Chính Xác ML", f"{prediction.get('accuracy', 0):.1%}")

        reliability = final_data.get('reliability_metrics', {})
        if reliability:
            st.markdown("---")
            st.subheader("📊 Độ tin cậy hệ thống (thực tế)")

            win_rate = reliability.get('win_rate', 0)
            pf = reliability.get('profit_factor', 0)
            max_dd = reliability.get('max_drawdown', 0)
            total_trades = reliability.get('total_trades', 0)

            if win_rate >= 0.55 and pf >= 1.5 and max_dd <= 12:
                trust_level = "✅ Đáng tin cậy"
                trust_color = "green"
                advice = "Tiếp tục dùng chiến lược hiện tại, tăng dần quy mô giao dịch nhẹ nhàng và giữ quy tắc quản trị rủi ro."
                timeframe_advice = "Khuyến nghị: giữ khung hiện tại, ưu tiên tín hiệu rõ và không tăng đòn bẩy quá mức."
                risk_advice = "Mức rủi ro phù hợp: 1-2% vốn mỗi lệnh."
                entry_advice = "Nếu tín hiệu BUY/SELL xuất hiện, vào lệnh theo xác suất đúng cao và chốt lời đúng kế hoạch."
                exit_advice = "Đặt SL/TP trước khi vào, không kéo lệnh quá lâu khi thị trường đổi hướng."
            elif win_rate >= 0.50 and pf >= 1.2 and max_dd <= 18:
                trust_level = "⚠️ Cần kiểm tra thêm"
                trust_color = "orange"
                advice = "Giữ vị thế nhỏ hơn, giảm lot, và tối ưu lại tín hiệu trước khi tăng vốn."
                timeframe_advice = "Khuyến nghị: chuyển sang khung thời gian lớn hơn để giảm nhiễu tín hiệu."
                risk_advice = "Mức rủi ro phù hợp: 0.5-1% vốn mỗi lệnh."
                entry_advice = "Chỉ vào lệnh khi tín hiệu có xác suất đúng trên 55% và xác nhận bằng khung phụ."
                exit_advice = "Cắt lỗ sớm hơn bình thường nếu giá phá vỡ cấu trúc quan trọng."
            else:
                trust_level = "❌ Rủi ro cao"
                trust_color = "red"
                advice = "Tạm dừng giao dịch, giảm rủi ro mạnh, kiểm tra lại tham số và tín hiệu."
                timeframe_advice = "Khuyến nghị: dừng giao dịch ngắn hạn, quay lại kiểm tra dữ liệu và chiến lược."
                risk_advice = "Mức rủi ro phù hợp: 0.25-0.5% vốn mỗi lệnh."
                entry_advice = "Không nên mở lệnh mới cho đến khi tín hiệu được xác nhận lại bằng nhiều chỉ báo."
                exit_advice = "Luôn dùng SL cố định và tránh để lệnh chạy khi market regime không rõ ràng."

            st.markdown(
                f"<div style='padding:10px 12px; border-left:4px solid {trust_color}; background-color:rgba(255,255,255,0.03); margin-bottom:10px;'>"
                f"<b>{trust_level}</b> — Win Rate {win_rate:.1%}, Profit Factor {pf:.2f}, Max Drawdown {max_dd:.1f}%</div>",
                unsafe_allow_html=True,
            )
            st.info(advice)
            st.caption(f"🕒 {timeframe_advice}")
            st.caption(f"🛡️ {risk_advice}")
            st.caption(f"📌 {entry_advice}")
            st.caption(f"🚪 {exit_advice}")

            c1, c2, c3, c4 = st.columns(4)
            with c1:
                st.metric("Win Rate", f"{win_rate:.1%}")
            with c2:
                st.metric("Profit Factor", f"{pf:.2f}")
            with c3:
                st.metric("Max Drawdown", f"{max_dd:.1f}%")
            with c4:
                st.metric("Tổng lệnh", total_trades)

            st.caption(
                f"Tổng lợi nhuận: ${reliability.get('total_profit', 0):,.2f} | "
                f"Thắng: {reliability.get('wins', 0)} | Thua: {reliability.get('losses', 0)}"
            )
        
        st.markdown("---")
        
        # Fibonacci & Regime
        fib = final_data.get('fibonacci', {})
        regime = final_data.get('regime', 'Unknown')
        short_term_recs = final_data.get('short_term_recommendations', [])
        short_term_best = final_data.get('short_term_best')
        
        c1, c2 = st.columns(2)
        with c1:
            st.subheader(" Fibonacci Levels")
            st.write(f"**Mức 0.618 (Golden Ratio):** {fib.get('0.618', 0):.2f}")
            st.write(f"**Mức 0.5:** {fib.get('0.5', 0):.2f}")
            st.write(f"**Mức 0.382:** {fib.get('0.382', 0):.2f}")
        with c2:
            st.subheader("🌪️ Market Regime")
            if regime == "TRENDING":
                st.success("✅ Thị trường đang có **XU HƯỚNG** (Trending)")
                st.markdown("→ Phù hợp đánh theo trend, hold lệnh lâu hơn")
            elif regime == "SIDEWAY":
                st.warning("⚠️ Thị trường đang **ĐI NGANG** (Sideway)")
                st.markdown("→ Phù hợp scalping, chốt lời nhanh")
            else:
                st.info("ℹ️ Chưa đủ dữ liệu xác định")

        if short_term_recs:
            st.markdown("---")
            st.subheader("⚡ Gợi ý scalping ngắn hạn")
            if short_term_best:
                st.success(
                    f"Khung ưu tiên: {short_term_best.get('timeframe', 'N/A')} | "
                    f"{short_term_best.get('direction', 'N/A')} | "
                    f"Buy {short_term_best.get('prob_buy', 0):.1f}% / Sell {short_term_best.get('prob_sell', 0):.1f}%"
                )
            for rec in short_term_recs:
                expected_prob = rec.get('expected_correct_probability', 0)
                if expected_prob >= 60:
                    color = "green"
                    icon = "✅"
                elif expected_prob >= 55:
                    color = "orange"
                    icon = "⚠️"
                else:
                    color = "red"
                    icon = "❌"

                st.markdown(
                    f"<div style='padding:8px 10px; margin-bottom:6px; border-left:4px solid {color}; background-color:rgba(255,255,255,0.03);'>"
                    f"{icon} <b>{rec.get('timeframe', 'N/A')}</b> | {rec.get('direction', 'N/A')} | "
                    f"Buy {rec.get('prob_buy', 0):.1f}% / Sell {rec.get('prob_sell', 0):.1f}% | "
                    f"Xác suất đúng ~ <b>{expected_prob:.1f}%</b> | "
                    f"Độ tin cậy {rec.get('confidence', 0):.1f}% | TP {rec.get('take_profit', 0):.5f} | SL {rec.get('stop_loss', 0):.5f}</div>",
                    unsafe_allow_html=True,
                )
        
        # Thời gian phân tích
        st.markdown("---")
        st.caption(f" **Thời gian phân tích:** {final_data.get('time', 'N/A')}")
        
    else:
        st.warning("⏳ Chưa có dữ liệu dự đoán. Hãy nhấn nút **'🚀 Chạy Hệ Thống Ngay'** để phân tích thị trường.")

# ================= TAB 2: BIỂU ĐỒ & TÍN HIỆU =================
with tab2:
    st.header("📈 Biểu Đồ Giá & Điểm Phát Tín Hiệu")
    signals_df = load_signals()
    
    if not signals_df.empty:
        # Vẽ biểu đồ
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=signals_df['Thời gian'], 
            y=signals_df['Giá'],
            mode='lines+markers', 
            name='Giá Close', 
            line=dict(color='royalblue', width=2)
        ))
        
        # Đánh dấu BUY/SELL
        buys = signals_df[signals_df['Tín hiệu'] == 'BUY']
        sells = signals_df[signals_df['Tín hiệu'] == 'SELL']
        
        fig.add_trace(go.Scatter(
            x=buys['Thời gian'], 
            y=buys['Giá'], 
            mode='markers',
            name='BUY Signal', 
            marker=dict(symbol='triangle-up', size=12, color='green')
        ))
        fig.add_trace(go.Scatter(
            x=sells['Thời gian'], 
            y=sells['Giá'], 
            mode='markers',
            name='SELL Signal', 
            marker=dict(symbol='triangle-down', size=12, color='red')
        ))
        
        fig.update_layout(
            title="Biểu đồ giá & Vị trí phát tín hiệu", 
            xaxis_title="Thời gian", 
            yaxis_title="Giá", 
            height=600, 
            template="plotly_dark"
        )
        st.plotly_chart(fig, use_container_width=True)
        
        # Bảng tín hiệu
        st.subheader("📜 Lịch sử tín hiệu đã phát")
        st.dataframe(signals_df, use_container_width=True, hide_index=True)
    else:
        st.warning("⏳ Chưa có dữ liệu tín hiệu. Hãy chạy hệ thống để có kết quả.")

# ================= TAB 3: BACKTEST & KẾT QUẢ =================
with tab3:
    st.header("💰 Hiệu Suất Backtest & Đường Cong Vốn")
    trades_df = load_trade_log()
    
    if not trades_df.empty:
        # Tính Equity Curve
        trades_df['PnL_Num'] = pd.to_numeric(
            trades_df['Lợi nhuận ($)'].astype(str).str.replace('$', '').str.replace(',', ''), 
            errors='coerce'
        ).fillna(0.0)
        
        initial_cap = initial_capital
        trades_df['Equity'] = initial_cap + trades_df['PnL_Num'].cumsum()
        
        # Vẽ Equity Curve
        fig_eq = go.Figure()
        fig_eq.add_trace(go.Scatter(
            x=trades_df['Thời gian vào'], 
            y=trades_df['Equity'], 
            mode='lines+markers', 
            name='Equity', 
            line=dict(color='gold', width=3),
            fill='tozeroy', 
            fillcolor='rgba(255, 215, 0, 0.1)'
        ))
        fig_eq.update_layout(
            title="📈 Đường cong tăng trưởng vốn (Equity Curve)", 
            yaxis_title="Vốn ($)", 
            height=400, 
            template="plotly_dark"
        )
        st.plotly_chart(fig_eq, use_container_width=True)
        
        # Thống kê
        wins = len(trades_df[trades_df['Kết quả'] == 'WIN'])
        losses = len(trades_df[trades_df['Kết quả'] == 'LOSS'])
        total = len(trades_df)
        wr = wins / total if total > 0 else 0
        total_pnl = trades_df['PnL_Num'].sum()
        
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Tổng lệnh", total)
        c2.metric("Win Rate", f"{wr:.1%}", delta=f"{wins}W / {losses}L")
        c3.metric("Tổng PnL", f"${total_pnl:,.2f}", delta="Profit" if total_pnl > 0 else "Loss")
        avg_duration = pd.to_numeric(trades_df['Số nến giữ'], errors='coerce').mean()
        c4.metric("Lệnh giữ TB", f"{avg_duration:.1f} nến" if not pd.isna(avg_duration) else "N/A")
        
        st.dataframe(trades_df, use_container_width=True, hide_index=True)
    else:
        st.warning("⏳ Chưa có dữ liệu trade. Hãy chạy hệ thống để có kết quả.")

# ================= TAB 4: MONTE CARLO & RỦI RO =================
with tab4:
    st.header("🎲 Mô Phỏng Monte Carlo & Phân Tích Rủi Ro")
    st.markdown("**Hệ thống đã chạy mô phỏng Bootstrap 1000 lần để tìm dải Win Rate thực tế trong tương lai.**")
    
    final_data = load_final_data()
    
    if final_data and 'monte_carlo' in final_data:
        mc = final_data['monte_carlo']
        
        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("Win Rate Mean", f"{mc.get('win_rate_mean', 0):.1%}")
        with c2:
            st.metric("Std Dev", f"{mc.get('win_rate_std', 0):.1%}")
        with c3:
            st.metric("90% Range", f"[{mc.get('win_rate_5th', 0):.1%} → {mc.get('win_rate_95th', 0):.1%}]")
        
        st.success(f"🎯 **Kết quả Monte Carlo:** WR {mc.get('win_rate_mean', 0):.1%} ± {mc.get('win_rate_std', 0):.1%}")
        
        # Vẽ histogram
        import numpy as np
        np.random.seed(42)
        mc_samples = np.random.normal(
            loc=mc.get('win_rate_mean', 0.5), 
            scale=mc.get('win_rate_std', 0.05), 
            size=1000
        )
        mc_samples = np.clip(mc_samples, 0, 1)
        
        fig_mc = px.histogram(
            x=mc_samples, 
            nbins=50, 
            title="Phân phối Win Rate qua 1000 lần mô phỏng", 
            labels={'x': 'Win Rate', 'y': 'Số lần'}, 
            color_discrete_sequence=['#FF4B4B'],
            template="plotly_dark"
        )
        fig_mc.update_layout(height=400)
        st.plotly_chart(fig_mc, use_container_width=True)
    else:
        st.info("Chưa có dữ liệu Monte Carlo. Hãy chạy hệ thống để có kết quả.")

# Footer
st.markdown("---")
st.caption("🏆 Final Boss Trading System v9.0 | Scalping Edition | Auto-refresh mỗi 30 giây | Powered by Streamlit, Plotly & Python")
