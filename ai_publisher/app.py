# app.py - Streamlit 主界面
#
# 三个 Tab：
#   - 任务看板：所有任务状态一览，支持筛选
#   - 审核队列：逐平台查看/编辑 AI 生成内容，选贴吧吧名，确认公众号扫码
#   - 新建任务：上传内容和图片，选择平台，触发 AI 处理
#
# 线程安全策略：
#   - AI处理 和 发布 都在独立子进程中运行（subprocess.Popen）
#   - Streamlit 只读取 JSON 文件，不共享内存
#   - 通过 st.rerun() + time.sleep() 实现轮询刷新

import sys
import time
import shutil
import subprocess
from pathlib import Path
from datetime import datetime

import streamlit as st

# 把项目根目录加入 path
sys.path.insert(0, str(Path(__file__).parent))

import config
import task_manager
from config import TaskStatus, PublishStatus, STATUS_LABELS
from platform_registry import PlatformRegistry

# ─────────────────────────────────────────────
# 页面基础配置
# ─────────────────────────────────────────────

st.set_page_config(
    page_title="AI 多平台发布工具",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded",
)

# 简洁的自定义样式
st.markdown("""
<style>
.status-badge {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 12px;
    font-size: 13px;
    font-weight: 500;
}
.platform-card {
    border: 1px solid #e0e0e0;
    border-radius: 8px;
    padding: 16px;
    margin-bottom: 12px;
    background: #fafafa;
}
.warn-box {
    background: #fff8e1;
    border-left: 4px solid #ffa000;
    padding: 10px 14px;
    border-radius: 4px;
    margin-bottom: 8px;
}
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# 启动配置校验
# ─────────────────────────────────────────────

ok, errors = config.validate_config()
if not ok:
    for e in errors:
        st.error(f"❌ 配置错误：{e}")
    st.info("请编辑 ai_publisher/.env 文件，参考 ai_publisher/.env.example 填入正确的值")
    st.stop()

# ─────────────────────────────────────────────
# 确保所有平台已注册（副作用导入）
# ─────────────────────────────────────────────

import publishers as _pubs  # noqa: E402,F401

# key → 显示名的便捷函数
def _platform_name(key: str) -> str:
    return PlatformRegistry.key_to_name(key)


# ─────────────────────────────────────────────
# 侧边栏：账号管理
# ─────────────────────────────────────────────

with st.sidebar:
    st.title("🚀 AI 发布工具")
    st.divider()
    st.subheader("👤 账号管理")

    for key, desc in PlatformRegistry.items():
        if desc.key == "mock":
            continue  # 模拟发布不显示在侧边栏
        name = desc.name
        pub = desc.publisher_class()
        logged_in = pub.is_logged_in()

        col1, col2 = st.columns([2, 1])
        with col1:
            if logged_in:
                st.success(f"✅ {name} {desc.logged_in_label}")
            else:
                st.error(f"❌ {name} 未登录")
        with col2:
            if st.button(desc.sidebar_btn_label, key=f"login_{key}"):
                pub.start_login_subprocess()
                msg = desc.login_message or f"已打开{name}登录窗口，请扫码后等待浏览器自动关闭"
                st.info(msg)

    st.divider()
    if st.button("🔄 刷新登录状态"):
        st.rerun()

    st.divider()
    st.caption(f"AI 模型：{config.AI_MODEL}")
    st.caption(f"API：{config.AI_BASE_URL}")

# ─────────────────────────────────────────────
# 主区域：三个 Tab
# ─────────────────────────────────────────────

tab_board, tab_review, tab_new = st.tabs(["📋 任务看板", "📝 审核队列", "✨ 新建任务"])


# ══════════════════════════════════════════════
# Tab 3：新建任务
# ══════════════════════════════════════════════

with tab_new:
    st.header("✨ 新建任务")

    col_left, col_right = st.columns([3, 2])

    with col_left:
        # 内容输入
        content_input = st.text_area(
            "📄 原始内容（粘贴文本，或配合下方上传文件）",
            height=220,
            placeholder="在这里粘贴你的文章、笔记、想法……"
        )

        # 文件上传（读取文本内容）
        uploaded_txt = st.file_uploader(
            "或上传文本文件（.txt / .md）",
            type=["txt", "md"],
            key="content_file"
        )
        if uploaded_txt is not None:
            content_input = uploaded_txt.read().decode("utf-8", errors="replace")
            st.success(f"已读取文件：{uploaded_txt.name}（{len(content_input)} 字）")

    with col_right:
        # 图片上传
        uploaded_images = st.file_uploader(
            "🖼️ 上传配图（可多选，最多9张）",
            type=["jpg", "jpeg", "png", "webp"],
            accept_multiple_files=True,
            key="images"
        )
        if uploaded_images:
            st.caption(f"已选 {len(uploaded_images)} 张图片")
            # 预览前两张
            preview_cols = st.columns(min(len(uploaded_images), 3))
            for i, img in enumerate(uploaded_images[:3]):
                with preview_cols[i]:
                    st.image(img, use_column_width=True)

        # 平台选择（从注册表动态生成）
        st.markdown("**🎯 选择发布平台**")
        platform_selections = {}
        for key, desc in PlatformRegistry.items():
            if key == "mock" and not config.SIMULATED_MODE:
                continue  # 非模拟模式下隐藏模拟发布
            default_on = key in ("xiaohongshu", "zhihu")
            platform_selections[key] = st.checkbox(
                f"{desc.icon} {desc.name}",
                value=default_on
            )
            # 需要手动扫码的平台显示警告
            if platform_selections[key] and desc.needs_warning_in_review and desc.review_warning:
                st.markdown(
                    f'<div class="warn-box">⚠️ {desc.review_warning}</div>',
                    unsafe_allow_html=True
                )

    # 提交按钮
    st.divider()
    if st.button("🤖 开始 AI 处理", type="primary", use_container_width=True):
        # 验证
        if not content_input or not content_input.strip():
            st.error("请先输入或上传内容")
            st.stop()

        selected_platforms = [k for k, v in platform_selections.items() if v]

        if not selected_platforms:
            st.error("请至少选择一个平台")
            st.stop()

        # 保存上传的图片到 uploads 目录
        image_paths = []
        for img_file in (uploaded_images or [])[:9]:
            dest = config.UPLOADS_DIR / img_file.name
            dest.write_bytes(img_file.getvalue())
            # 存相对路径
            image_paths.append(str(dest.relative_to(config.DATA_DIR)))

        try:
            # 创建任务
            task = task_manager.create_task(
                original_content=content_input.strip(),
                platforms=selected_platforms,
                images=image_paths,
            )

            # 启动 AI 处理子进程
            import ai_processor
            ai_processor.start_processing(task["id"])

            st.success(f"✅ 任务已创建（ID: {task['id']}），AI 正在处理中…")
            st.info("请切换到「任务看板」查看进度，或切换到「审核队列」等待 AI 完成")
            time.sleep(1)
            st.rerun()
        except Exception as e:
            st.error(f"❌ 任务创建失败：{e}")


# ══════════════════════════════════════════════
# Tab 1：任务看板
# ══════════════════════════════════════════════

with tab_board:
    st.header("📋 任务看板")

    col_refresh, col_filter = st.columns([1, 3])
    with col_refresh:
        if st.button("🔄 刷新"):
            st.rerun()
    with col_filter:
        status_filter = st.selectbox(
            "筛选状态",
            ["全部"] + list(STATUS_LABELS.values()),
            label_visibility="collapsed"
        )

    try:
        tasks = task_manager.load_all_tasks()
    except Exception as e:
        st.error(f"❌ 加载任务列表失败：{e}")
        tasks = []

    # 筛选
    if status_filter != "全部":
        reverse_labels = {v: k for k, v in STATUS_LABELS.items()}
        target_status = reverse_labels.get(status_filter)
        tasks = [t for t in tasks if t.get("status") == target_status]

    if not tasks:
        st.info("暂无任务，去「新建任务」创建第一个吧 🎉")
    else:
        # 有进行中的任务时，自动刷新
        active_statuses = {TaskStatus.ANALYZING, TaskStatus.PUBLISHING}
        has_active = any(t.get("status") in active_statuses for t in tasks)
        if has_active:
            st.caption("🔄 有任务处理中，每5秒自动刷新")
            time.sleep(5)
            st.rerun()

        for task in tasks[:50]:
            status = task.get("status", "")
            status_label = STATUS_LABELS.get(status, status)
            created = task.get("created_at", "")[:16].replace("T", " ")
            platforms_str = " / ".join(
                _platform_name(p) for p in task.get("platforms", [])
            )
            content_preview = task.get("original_content", "")[:60].replace("\n", " ")

            with st.expander(
                f"{status_label}  |  {created}  |  {platforms_str}  |  {content_preview}…",
                expanded=(status == TaskStatus.PENDING_REVIEW)
            ):
                # 分析结果
                if task.get("analysis"):
                    ana = task["analysis"]
                    st.markdown(
                        f"**主题：** {ana.get('topic', '-')}　"
                        f"**类型：** {ana.get('content_type', '-')}　"
                        f"**情感：** {ana.get('emotion', '-')}"
                    )
                    st.caption("热词：" + "、".join(ana.get("hot_words", [])))

                # 发布结果
                if task.get("publish_results"):
                    st.markdown("**发布结果：**")
                    for plat, res in task["publish_results"].items():
                        plat_name = _platform_name(plat)
                        pstatus = res.get("status", "")
                        if pstatus == PublishStatus.SUCCESS:
                            url = res.get("url", "")
                            st.success(f"✅ {plat_name}：[查看链接]({url})" if url else f"✅ {plat_name}：已发布")
                        elif pstatus == PublishStatus.FAILED:
                            st.error(f"❌ {plat_name}：{res.get('error', '失败')}")
                        elif pstatus == PublishStatus.SKIPPED:
                            st.warning(f"⏭ {plat_name}：已跳过")
                        else:
                            st.info(f"⏳ {plat_name}：待发布")

                # 错误信息
                if task.get("error"):
                    st.error(f"错误：{task['error']}")

                # 操作按钮
                btn_col1, btn_col2 = st.columns(2)
                with btn_col1:
                    if task["status"] == TaskStatus.FAILED:
                        if st.button("🔁 重新处理", key=f"retry_{task['id']}"):
                            import ai_processor
                            task_manager.update_status(task["id"], TaskStatus.CREATED)
                            ai_processor.start_processing(task["id"])
                            st.rerun()
                with btn_col2:
                    if st.button("🗑️ 删除", key=f"del_{task['id']}"):
                        task_manager.delete_task(task["id"])
                        st.rerun()


# ══════════════════════════════════════════════
# Tab 2：审核队列
# ══════════════════════════════════════════════

with tab_review:
    st.header("📝 审核队列")

    if st.button("🔄 刷新", key="refresh_review"):
        st.rerun()

    try:
        tasks = task_manager.load_all_tasks()
    except Exception as e:
        st.error(f"❌ 加载任务列表失败：{e}")
        tasks = []
    pending_tasks = [t for t in tasks if t.get("status") == TaskStatus.PENDING_REVIEW]

    # 同时也显示 analyzing 状态，告知用户等待
    analyzing_tasks = [t for t in tasks if t.get("status") == TaskStatus.ANALYZING]
    if analyzing_tasks:
        st.info(f"🤖 {len(analyzing_tasks)} 个任务正在 AI 处理中，完成后会出现在这里…（可点刷新）")

    if not pending_tasks:
        if not analyzing_tasks:
            st.info("暂无待审核内容")
    else:
        for task in pending_tasks:
            content_preview = task.get("original_content", "")[:80].replace("\n", " ")
            st.subheader(f"任务 {task['id']}  —  {content_preview}…")

            platforms = task.get("platforms", [])
            ai_results = task.get("ai_results", {})
            review_state = task.get("review", {})

            # 逐平台展示
            for platform in platforms:
                desc = PlatformRegistry.get(platform)
                plat_name = desc.name if desc else platform
                content = ai_results.get(platform, {})
                is_approved = review_state.get(platform) == "approved"

                # 平台卡片
                st.markdown(f'<div class="platform-card">', unsafe_allow_html=True)
                header_col, status_col = st.columns([4, 1])
                with header_col:
                    icon = desc.icon if desc else "📄"
                    st.markdown(f"### {icon} {plat_name}")
                with status_col:
                    if is_approved:
                        st.success("✅ 已通过")
                    else:
                        st.warning("⏳ 待审核")

                # 手动扫码/额外警告
                if desc and desc.needs_warning_in_review and not is_approved:
                    warning = desc.review_warning or "该平台发布时需要额外确认"
                    st.markdown(
                        f'<div class="warn-box">⚠️ {warning}</div>',
                        unsafe_allow_html=True
                    )

                # 社区/吧名选择
                if desc and desc.has_bar_selection and not is_approved:
                    candidates = content.get("tieba_candidates", [])
                    current_selection = content.get("tieba_selected")

                    if candidates:
                        selected_bar = st.radio(
                            "📍 选择发布到哪个社区（AI推荐）",
                            options=candidates,
                            index=candidates.index(current_selection) if current_selection in candidates else 0,
                            horizontal=True,
                            key=f"bar_select_{task['id']}_{platform}"
                        )
                        if selected_bar != current_selection:
                            task_manager.set_platform_extra_field(
                                task["id"], platform, "tieba_selected", selected_bar
                            )
                    else:
                        custom_bar = st.text_input(
                            "输入目标社区名称",
                            value=current_selection or "",
                            key=f"bar_custom_{task['id']}_{platform}"
                        )
                        if custom_bar:
                            task_manager.set_platform_extra_field(
                                task["id"], platform, "tieba_selected", custom_bar
                            )

                # 可编辑的标题
                edited_title = st.text_input(
                    "标题",
                    value=content.get("title", ""),
                    disabled=is_approved,
                    key=f"title_{task['id']}_{platform}"
                )

                # 可编辑的正文
                body_key = "body"
                edited_body = st.text_area(
                    "正文",
                    value=content.get(body_key, ""),
                    height=180,
                    disabled=is_approved,
                    key=f"body_{task['id']}_{platform}"
                )

                # 标签（仅部分平台有）
                if "tags" in content:
                    edited_tags_str = st.text_input(
                        "标签（逗号分隔）",
                        value="，".join(content.get("tags", [])),
                        disabled=is_approved,
                        key=f"tags_{task['id']}_{platform}"
                    )

                # 操作按钮
                if not is_approved:
                    btn1, btn2, btn3 = st.columns(3)
                    with btn1:
                        if st.button(f"✅ 通过", key=f"approve_{task['id']}_{platform}"):
                            # 收集编辑后的内容
                            edited = {"title": edited_title, body_key: edited_body}
                            if "tags" in content:
                                raw_tags = edited_tags_str if "tags" in content else ""
                                edited["tags"] = [t.strip() for t in raw_tags.replace("，", ",").split(",") if t.strip()]
                            task_manager.approve_platform(task["id"], platform, edited)
                            st.rerun()

                    with btn2:
                        if st.button(f"🔄 重来", key=f"regen_{task['id']}_{platform}"):
                            with st.spinner(f"正在重新生成 {plat_name} 内容..."):
                                try:
                                    import ai_processor
                                    loaded = task_manager.load_task(task["id"])
                                    if loaded is None:
                                        st.error("任务文件不存在")
                                    else:
                                        new_content = ai_processor.regenerate_single(
                                            loaded["original_content"],
                                            platform,
                                            loaded.get("analysis", {})
                                        )
                                        loaded["ai_results"][platform] = new_content
                                        task_manager.save_task(loaded)
                                        st.rerun()
                                except Exception as e:
                                    st.error(f"重新生成失败：{e}")

                    with btn3:
                        if st.button(f"⏭ 跳过", key=f"skip_{task['id']}_{platform}"):
                            task_manager.reject_platform(task["id"], platform)
                            # 标记为跳过发布
                            task_manager.update_publish_result(
                                task["id"], platform,
                                status=PublishStatus.SKIPPED,
                                error="用户跳过"
                            )
                            st.rerun()

                st.markdown('</div>', unsafe_allow_html=True)

            # 检查是否全部平台已处理（通过 or 跳过）
            loaded = task_manager.load_task(task["id"])
            if loaded is None:
                st.warning("任务文件已丢失，请刷新")
                continue
            review = loaded.get("review", {})
            all_handled = all(v in ("approved", "rejected") for v in review.values())
            any_approved = any(v == "approved" for v in review.values())

            if all_handled and any_approved:
                st.divider()
                approved_names = [_platform_name(p) for p, v in review.items() if v == "approved"]
                st.info(f"✅ 以下平台已通过审核，可以发布：{', '.join(approved_names)}")

                if st.button(f"🚀 开始发布", type="primary", key=f"publish_{task['id']}"):
                    # 启动发布子进程
                    subprocess.Popen(
                        [sys.executable, str(Path(__file__).parent / "publisher_runner.py"), task["id"]],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    task_manager.update_status(task["id"], TaskStatus.PUBLISHING)
                    st.success("🚀 发布任务已启动，请到「任务看板」查看进度")
                    time.sleep(1)
                    st.rerun()
            elif all_handled and not any_approved:
                st.warning("所有平台都被跳过，任务已关闭")
                task_manager.update_status(task["id"], TaskStatus.FAILED, error="所有平台被跳过")

            st.divider()
