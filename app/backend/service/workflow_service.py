import asyncio
import logging
import time
from threading import Lock, Thread
from typing import AsyncIterator, Callable

logger = logging.getLogger("workflow_service")

from ...mult_agents.config import AppConfig
from ...mult_agents.graph import build_app as build_workflow_app
from ...mult_agents.main import build_agents, build_checkpointer, build_memory_manager
from ...mult_agents.state import create_initial_state
from ...mult_agents.usage import aggregate_usage
from ...mult_agents.research_profile import resolve_research_domain, source_summary
from ..report_store import ReportStore


class WorkflowService:
    def __init__(self, config_path: str):
        self._config_path = config_path
        self._lock = Lock()
        self._thread_locks: dict[str, Lock] = {}
        self._report_store = ReportStore()
        self._initialized = False
        self._base_config: AppConfig | None = None
        self._memory_manager = None
        self._app = None

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        with self._lock:
            if self._initialized:
                return
            base_config = AppConfig.load(self._config_path)
            self._memory_manager = build_memory_manager(base_config)
            agents = build_agents(base_config.model, base_config.api_key, base_config.base_url, base_config)
            checkpointer = build_checkpointer(base_config)
            self._app = build_workflow_app(agents, checkpointer)
            self._base_config = base_config
            self._initialized = True

    def _memory_manager_for(self, runtime_config: AppConfig):
        """基础配置未开启记忆但请求开启时，按运行时配置懒加载记忆管理器。"""
        if self._memory_manager is not None:
            return self._memory_manager
        if not runtime_config.enable_memory:
            return None
        with self._lock:
            if self._memory_manager is None:
                self._memory_manager = build_memory_manager(runtime_config)
        return self._memory_manager

    def _thread_lock(self, thread_id: str) -> Lock:
        """同一 thread_id 的并发请求串行执行，避免共享 checkpointer 状态互相覆盖。"""
        with self._lock:
            lock = self._thread_locks.get(thread_id)
            if lock is None:
                if len(self._thread_locks) >= 256:
                    self._thread_locks.clear()
                lock = self._thread_locks.setdefault(thread_id, Lock())
            return lock

    def _build_runtime_config(
        self,
        user_id: str,
        thread_id: str,
        tenant_id: str,
        max_iterations: int | None,
        enable_memory: bool | None,
    ) -> AppConfig:
        if self._base_config is None:
            raise RuntimeError("service not initialized")
        overrides = {
            "user_id": user_id,
            "thread_id": thread_id,
            "tenant_id": tenant_id,
            "max_iterations": max_iterations if max_iterations is not None else self._base_config.max_iterations,
        }
        if enable_memory is not None:
            overrides["enable_memory"] = enable_memory
        return self._base_config.with_overrides(**overrides)

    def _run_sync(
        self,
        query: str,
        user_id: str,
        thread_id: str,
        tenant_id: str,
        max_iterations: int | None,
        enable_memory: bool | None,
        research_domain: str = "auto",
    ) -> tuple[str, str, dict, dict, dict]:
        self._ensure_initialized()
        runtime_config = self._build_runtime_config(
            user_id=user_id,
            thread_id=thread_id,
            tenant_id=tenant_id,
            max_iterations=max_iterations,
            enable_memory=enable_memory,
        )
        memory_manager = self._memory_manager_for(runtime_config)
        memory_context = ""
        if memory_manager and runtime_config.enable_memory:
            memory_context = memory_manager.build_personalized_prompt_context(
                user_id=runtime_config.user_id,
                thread_id=runtime_config.thread_id,
                query=query,
                tenant_id=runtime_config.tenant_id,
                max_memories=runtime_config.memory_top_k,
            )
        else:
            memory_context = ""
        state = create_initial_state(
            query=query,
            max_iterations=runtime_config.max_iterations,
            user_id=runtime_config.user_id,
            tenant_id=runtime_config.tenant_id,
            memory_context=memory_context,
            research_domain=research_domain,
        )
        t0 = time.time()
        with self._thread_lock(runtime_config.thread_id):
            result = self._app.invoke(
                state,
                {"configurable": {"thread_id": runtime_config.thread_id}},
            )
        total_elapsed = time.time() - t0
        logger.info("[workflow] 总耗时: %.1fs | query=%s | iterations=%s", total_elapsed, query[:60], result.get("iteration", "?"))
        final = result.get("final", "")
        route = str(result.get("intent", "multiagent"))
        usage_log = result.get("usage_log", [])
        if usage_log:
            logger.info("[workflow] 用量: %s", aggregate_usage(usage_log))
        quality_report = result.get("quality_report", {})
        evidence_summary = source_summary(result.get("evidence_pool", []), result.get("source_index", []))
        resolved_domain = resolve_research_domain(research_domain, query)
        report_id = None
        try:
            report_id = self._report_store.save(
                {
                    "query": query,
                    "user_id": runtime_config.user_id,
                    "thread_id": runtime_config.thread_id,
                    "tenant_id": runtime_config.tenant_id,
                    "final": final,
                    "usage": aggregate_usage(usage_log),
                    "quality": quality_report,
                    "research_domain": resolved_domain,
                    "evidence_summary": evidence_summary,
                }
            )
        except Exception as exc:
            logger.warning("保存报告历史失败: %s", exc)
        if memory_manager and runtime_config.enable_memory:
            memory_manager.persist_turn(
                tenant_id=runtime_config.tenant_id,
                user_id=runtime_config.user_id,
                thread_id=runtime_config.thread_id,
                query=query,
                answer=final,
            )
        return final, route, aggregate_usage(usage_log), quality_report, {
            "report_id": report_id,
            "research_domain": resolved_domain,
            "evidence_summary": evidence_summary,
            "trace": [],
        }

    @staticmethod
    def _node_message(node_name: str) -> str:
        mapping = {
            "intent": "Intent Router 正在识别问题意图",
            "direct_answer": "Direct Responder 正在快速作答",
            "plan": "Planner 正在拆解问题",
            "web_search": "Web Scout 正在检索网络证据",
            "local_rag": "Local Scout 正在检索本地知识库",
            "deep_dive": "Evidence Judge 正在进行证据裁判",
            "analyze": "Analyst 正在生成结论",
            "reflect": "Reflect 正在生成补搜计划",
            "write": "Writer 正在撰写最终报告",
            "judge": "Judge 正在进行质量评审",
        }
        return mapping.get(node_name, f"{node_name} 正在执行")

    def _run_sync_with_events(
        self,
        query: str,
        user_id: str,
        thread_id: str,
        tenant_id: str,
        max_iterations: int | None,
        enable_memory: bool | None,
        emit: Callable[[dict], None],
        research_domain: str = "auto",
    ) -> tuple[str, str, dict, dict, dict]:
        self._ensure_initialized()
        runtime_config = self._build_runtime_config(
            user_id=user_id,
            thread_id=thread_id,
            tenant_id=tenant_id,
            max_iterations=max_iterations,
            enable_memory=enable_memory,
        )
        memory_manager = self._memory_manager_for(runtime_config)
        memory_context = ""
        if memory_manager and runtime_config.enable_memory:
            memory_context = memory_manager.build_personalized_prompt_context(
                user_id=runtime_config.user_id,
                thread_id=runtime_config.thread_id,
                query=query,
                tenant_id=runtime_config.tenant_id,
                max_memories=runtime_config.memory_top_k,
            )
        else:
            memory_context = ""
        state = create_initial_state(
            query=query,
            max_iterations=runtime_config.max_iterations,
            user_id=runtime_config.user_id,
            tenant_id=runtime_config.tenant_id,
            memory_context=memory_context,
            research_domain=research_domain,
        )
        final = ""
        route = "multiagent"
        usage_log: list[dict] = []
        quality_report: dict = {}
        trace: list[str] = []
        latest_state = dict(state)
        config = {"configurable": {"thread_id": runtime_config.thread_id}}
        lock = self._thread_lock(runtime_config.thread_id)
        lock.acquire()
        try:
            for update in self._app.stream(state, config, stream_mode="updates"):
                if not isinstance(update, dict):
                    continue
                for node_name, node_output in update.items():
                    if str(node_name) not in trace:
                        trace.append(str(node_name))
                    emit({"type": "phase", "node": node_name, "message": self._node_message(str(node_name))})
                    if isinstance(node_output, dict):
                        latest_state.update(node_output)
                        usage_log.extend(node_output.get("usage_log") or [])
                        if node_output.get("quality_report"):
                            quality_report = node_output["quality_report"]
                        if node_name == "intent":
                            detected = str(node_output.get("intent", route)).strip().lower()
                            if detected in {"direct", "multiagent"}:
                                route = detected
                        value = node_output.get("final")
                        if value:
                            final = str(value)
        finally:
            lock.release()
        if not final:
            # 不重复执行整个工作流：stream 已跑完但仍无 final 说明流程异常，直接报错
            raise RuntimeError("工作流执行完成但未产出最终报告，请查看服务端日志")
        usage_totals = aggregate_usage(usage_log)
        logger.info("[workflow] 用量: %s | 质量分: %s", usage_totals, quality_report.get("score", "-"))
        evidence_summary = source_summary(latest_state.get("evidence_pool", []), latest_state.get("source_index", []))
        resolved_domain = resolve_research_domain(research_domain, query)
        report_id = None
        try:
            report_id = self._report_store.save(
                {
                    "query": query,
                    "user_id": runtime_config.user_id,
                    "thread_id": runtime_config.thread_id,
                    "tenant_id": runtime_config.tenant_id,
                    "final": final,
                    "usage": usage_totals,
                    "quality": quality_report,
                    "research_domain": resolved_domain,
                    "evidence_summary": evidence_summary,
                    "trace": trace,
                }
            )
        except Exception as exc:
            logger.warning("保存报告历史失败: %s", exc)
        if memory_manager and runtime_config.enable_memory:
            memory_manager.persist_turn(
                tenant_id=runtime_config.tenant_id,
                user_id=runtime_config.user_id,
                thread_id=runtime_config.thread_id,
                query=query,
                answer=final,
            )
        return final, route, usage_totals, quality_report, {
            "report_id": report_id,
            "research_domain": resolved_domain,
            "evidence_summary": evidence_summary,
            "trace": trace,
        }

    async def run(
        self,
        query: str,
        user_id: str,
        thread_id: str,
        tenant_id: str,
        max_iterations: int | None,
        enable_memory: bool | None,
        research_domain: str = "auto",
    ) -> str:
        final, _, _, _, _ = await asyncio.to_thread(
            self._run_sync,
            query,
            user_id,
            thread_id,
            tenant_id,
            max_iterations,
            enable_memory,
            research_domain,
        )
        return final

    async def run_with_meta(
        self,
        query: str,
        user_id: str,
        thread_id: str,
        tenant_id: str,
        max_iterations: int | None,
        enable_memory: bool | None,
        research_domain: str = "auto",
    ) -> tuple[str, str, dict, dict, dict]:
        return await asyncio.to_thread(
            self._run_sync,
            query,
            user_id,
            thread_id,
            tenant_id,
            max_iterations,
            enable_memory,
            research_domain,
        )

    async def run_with_route(
        self,
        query: str,
        user_id: str,
        thread_id: str,
        tenant_id: str,
        max_iterations: int | None,
        enable_memory: bool | None,
        research_domain: str = "auto",
    ) -> tuple[str, str]:
        final, route, _, _, _ = await asyncio.to_thread(
            self._run_sync,
            query,
            user_id,
            thread_id,
            tenant_id,
            max_iterations,
            enable_memory,
            research_domain,
        )
        return final, route

    async def stream_events(
        self,
        query: str,
        user_id: str,
        thread_id: str,
        tenant_id: str,
        max_iterations: int | None,
        enable_memory: bool | None,
        research_domain: str = "auto",
    ) -> AsyncIterator[dict]:
        queue: asyncio.Queue[dict] = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def emit(event: dict) -> None:
            asyncio.run_coroutine_threadsafe(queue.put(event), loop)

        def worker() -> None:
            try:
                final, route, usage_totals, quality_report, meta = self._run_sync_with_events(
                    query=query,
                    user_id=user_id,
                    thread_id=thread_id,
                    tenant_id=tenant_id,
                    max_iterations=max_iterations,
                    enable_memory=enable_memory,
                    research_domain=research_domain,
                    emit=emit,
                )
                emit({"type": "route", "message": "已走直接回答路径" if route == "direct" else "已走多智能体研究路径"})
                emit(
                    {
                        "type": "final",
                        "query": query,
                        "user_id": user_id,
                        "thread_id": thread_id,
                        "tenant_id": tenant_id,
                        "final": final,
                        "usage": usage_totals,
                        "quality": quality_report,
                        **meta,
                    }
                )
            except Exception as exc:
                emit({"type": "error", "message": str(exc)})
            finally:
                emit({"type": "__done__"})

        Thread(target=worker, daemon=True).start()
        while True:
            event = await queue.get()
            if event.get("type") == "__done__":
                break
            yield event
