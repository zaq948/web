import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, date, timedelta


# ================= 数据库初始化 =================
def init_db():
    conn = sqlite3.connect('booking.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS bookings
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_name TEXT,
                  book_date TEXT,
                  start_time TEXT,
                  end_time TEXT,
                  submit_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS settings
                 (key TEXT PRIMARY KEY, value TEXT)''')
    conn.commit()
    conn.close()


init_db()


# ================= 核心工具函数 =================
def get_time_slots():
    slots = []
    start = datetime.strptime("08:00", "%H:%M")
    end = datetime.strptime("22:00", "%H:%M")
    while start <= end:
        slots.append(start.strftime("%H:%M"))
        start += timedelta(minutes=30)
    return slots


def get_weekday_cn(date_obj):
    weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    return weekdays[date_obj.weekday()]


def check_conflict(book_date, start_time, end_time):
    conn = sqlite3.connect('booking.db')
    c = conn.cursor()
    c.execute("SELECT start_time, end_time FROM bookings WHERE book_date=?", (book_date,))
    existing = c.fetchall()
    conn.close()
    for b_start, b_end in existing:
        if start_time < b_end and end_time > b_start:
            return True
    return False


# 获取系统设置
def get_settings():
    conn = sqlite3.connect('booking.db')
    c = conn.cursor()
    c.execute("SELECT key, value FROM settings")
    settings = {row[0]: row[1] for row in c.fetchall()}
    conn.close()
    return settings


# ================= 页面配置 =================
st.set_page_config(page_title="实验室机时预约", layout="wide")
st.title("🔬 实验室公共设备机时预约系统")

settings = get_settings()

# ================= 侧边栏：角色切换 =================
st.sidebar.title("控制面板")
role = st.sidebar.radio("选择身份", ["普通用户", "管理员"])

if role == "管理员":
    st.sidebar.subheader("👨‍💻 管理员登录")
    pwd = st.sidebar.text_input("请输入管理员密码", type="password")

    if pwd == "123456":
        st.success("管理员登录成功！")
        st.header("⚙️ 预约规则与放号设置")

        st.markdown("##### 1. 设置要开放的【机时日期范围】 (例如下周一到下周日)")
        col_d1, col_d2 = st.columns(2)
        with col_d1:
            target_start = st.date_input("允许预约的开始日期")
        with col_d2:
            target_end = st.date_input("允许预约的结束日期", value=target_start + timedelta(days=6))

        st.markdown("##### 2. 设置系统【开始放号的时间】")
        col_t1, col_t2 = st.columns(2)
        with col_t1:
            release_date = st.date_input("放号日期")
        with col_t2:
            # step=60 表示以1分钟为单位选择，满足你的第1点需求
            release_time = st.time_input("放号时间 (精确到分钟)", step=60)

        release_datetime = f"{release_date} {release_time.strftime('%H:%M:%S')}"

        if st.button("🚀 发布以上设置", use_container_width=True):
            conn = sqlite3.connect('booking.db')
            c = conn.cursor()
            c.execute("REPLACE INTO settings (key, value) VALUES ('release_time', ?)", (release_datetime,))
            c.execute("REPLACE INTO settings (key, value) VALUES ('target_start', ?)", (str(target_start),))
            c.execute("REPLACE INTO settings (key, value) VALUES ('target_end', ?)", (str(target_end),))
            conn.commit()
            conn.close()
            st.success(f"设置成功！系统将在 {release_datetime} 准时开放 {target_start} 至 {target_end} 的机时预约。")

        st.markdown("---")
        if st.button("🗑️ 清空所有历史预约记录 (危险)"):
            conn = sqlite3.connect('booking.db')
            c = conn.cursor()
            c.execute("DELETE FROM bookings")
            conn.commit()
            conn.close()
            st.warning("记录已清空！")
    elif pwd:
        st.error("密码错误！")

# ================= 普通用户界面 =================
elif role == "普通用户":
    if not settings.get('target_start') or not settings.get('release_time'):
        st.info("管理员尚未配置预约规则，请稍后再来。")
        st.stop()

    release_dt = datetime.strptime(settings['release_time'], "%Y-%m-%d %H:%M:%S")
    target_start_dt = datetime.strptime(settings['target_start'], "%Y-%m-%d").date()
    target_end_dt = datetime.strptime(settings['target_end'], "%Y-%m-%d").date()

    # --- 1. 无论是否到时间，都展示本周期“课程表”视图 (需求2 和 需求4) ---
    st.subheader(f"📅 机时预约视图 ({target_start_dt} 至 {target_end_dt})")

    # 构建日期列
    date_list = []
    current_d = target_start_dt
    while current_d <= target_end_dt:
        date_list.append(current_d)
        current_d += timedelta(days=1)

    col_names = [f"{d.strftime('%m-%d')} ({get_weekday_cn(d)})" for d in date_list]
    all_slots = get_time_slots()[:-1]  # 不包含最后一个作为起点的结束时刻 (即22:00)

    # 初始化空的 DataFrame
    df_grid = pd.DataFrame("🟢 空闲", index=all_slots, columns=col_names)

    # 填充已预约数据
    conn = sqlite3.connect('booking.db')
    df_bookings = pd.read_sql_query(
        "SELECT user_name, book_date, start_time, end_time FROM bookings WHERE book_date >= ? AND book_date <= ?", conn,
        params=(str(target_start_dt), str(target_end_dt)))
    conn.close()

    for _, row in df_bookings.iterrows():
        b_date = datetime.strptime(row['book_date'], "%Y-%m-%d").date()
        if b_date in date_list:
            col_idx = date_list.index(b_date)
            col_name = col_names[col_idx]
            s_time = row['start_time']
            e_time = row['end_time']
            name = row['user_name']

            # 将对应时间段标红
            for slot in all_slots:
                if s_time <= slot < e_time:
                    df_grid.at[slot, col_name] = f"🔴 {name}"

    # 展示类似Excel的视图
    st.dataframe(df_grid, use_container_width=True, height=500)

    st.markdown("---")

    # --- 2. 用户信息提前填写区域 (需求4) ---
    st.subheader("📝 预约操作区")
    st.info(f"💡 提示：您可以提前填好姓名。预约将于 **{settings['release_time']}** 准时开放。")

    col1, col2 = st.columns([1, 2])
    with col1:
        # 使用 key 保存状态，提前填写不受页面刷新影响
        user_name = st.text_input("1. 输入您的姓名 (必填)", placeholder="例如：张三", key="username_input")
        # 刷新按钮，用于到点后手动刷新出预约框
        if st.button("🔄 刷新最新状态/抢号"):
            st.rerun()

    with col2:
        now = datetime.now()
        if now < release_dt:
            # 未到时间
            st.warning(
                f"⏳ **预约尚未开放**\n\n系统将于 `{settings['release_time']}` 准时开放预约入口，请到点后点击左侧【刷新】按钮。")
        else:
            # 已经到时间，显示预约表单
            st.success("🟢 预约已开放！请尽快提交（先到先得）。")

            with st.form("booking_form"):
                f_col1, f_col2, f_col3 = st.columns(3)
                with f_col1:
                    book_date = st.date_input("选择日期", min_value=target_start_dt, max_value=target_end_dt)
                with f_col2:
                    start_time = st.selectbox("开始时间", all_slots)
                with f_col3:
                    valid_end_slots = [t for t in get_time_slots() if t > start_time]
                    end_time = st.selectbox("结束时间", valid_end_slots)

                submitted = st.form_submit_button("✅ 确认抢占机时", use_container_width=True)

                if submitted:
                    if not st.session_state.username_input:
                        st.error("❌ 姓名不能为空，请在左侧填写姓名！")
                    else:
                        # 检查冲突
                        if check_conflict(str(book_date), start_time, end_time):
                            st.error("❌ 预约失败！手慢了，该时间段与他人的预约冲突，请查看上方表格更新后重新选择。")
                        else:
                            # 写入数据库
                            conn = sqlite3.connect('booking.db')
                            c = conn.cursor()
                            c.execute(
                                "INSERT INTO bookings (user_name, book_date, start_time, end_time) VALUES (?, ?, ?, ?)",
                                (st.session_state.username_input, str(book_date), start_time, end_time))
                            conn.commit()
                            conn.close()
                            st.success("🎉 预约成功！点击【刷新】按钮即可在上方表格查看您的排期。")