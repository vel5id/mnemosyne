"""
Mnemosyne Core V3.0 - System Guardrails Module

Этот модуль реализует механизм "Smart Full Stop" для защиты производительности
системы пользователя. Проверяет доступность ресурсов GPU и активность пользователя
перед запуском тяжелых вычислений.

Использует pynvml для прямого опроса NVIDIA GPU без использования subprocess.
"""

import logging
from typing import Optional

try:
    import pynvml
except ImportError:
    pynvml = None

import psutil

logger = logging.getLogger(__name__)


class NVMLError(Exception):
    """Исключение для ошибок NVML."""
    pass


class SystemGuard:
    """
    Класс для проверки системных ресурсов и активности пользователя.

    Реализует защиту VRAM и детекцию запущенных игр/ресурсоемких приложений.
    """

    # Черный список процессов (игры и ресурсоемкие приложения)
    PROCESS_BLACKLIST = {
        # Игры Steam
        "cs2.exe",
        "dota2.exe",
        "csgo.exe",
        "rust.exe",
        "valheim.exe",
        "eldenring.exe",
        "cyberpunk2077.exe",
        "gta5.exe",
        "gta_v.exe",
        # Игры Epic/Origin/Uplay
        "fortnite.exe",
        "apex.exe",
        "battlefield.exe",
        "cod.exe",
        "blackops4.exe",
        # Ресурсоемкие приложения
        "blender.exe",
        "maya.exe",
        "3dsmax.exe",
        "afterfx.exe",
        "premiere.exe",
        # Виртуализация
        "vmware.exe",
        "virtualbox.exe",
        "qemu-system-x86_64.exe",
    }

    def __init__(self, vram_threshold_gb: float = 4.0):
        """
        Инициализация SystemGuard.

        Args:
            vram_threshold_gb: Минимальное количество свободной VRAM в ГБ
                               для запуска VLM (по умолчанию 4 ГБ).
        """
        self.vram_threshold_bytes = int(vram_threshold_gb * 1024 * 1024 * 1024)
        self.nvml_initialized = False
        self._init_nvml()

    def _init_nvml(self) -> None:
        """
        Инициализация NVML библиотеки.

        Вызывается один раз при создании экземпляра.
        Если NVML недоступен (нет NVIDIA GPU или драйверов),
        система продолжит работу без VRAM-проверок.
        """
        if pynvml is None:
            logger.warning("pynvml library not available. VRAM checks disabled.")
            return

        try:
            pynvml.nvmlInit()
            self.nvml_initialized = True
            device_count = pynvml.nvmlDeviceGetCount()
            logger.info(f"NVML initialized successfully. Found {device_count} GPU(s).")
        except pynvml.NVMLError as e:
            logger.warning(f"Failed to initialize NVML: {e}. VRAM checks disabled.")
        except Exception as e:
            logger.error(f"Unexpected error initializing NVML: {e}")

    def get_free_vram_bytes(self) -> Optional[int]:
        """
        Получить количество свободной видеопамяти в байтах.

        Returns:
            Количество свободных байт VRAM или None, если NVML недоступен.
        """
        if not self.nvml_initialized or pynvml is None:
            return None

        try:
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            info = pynvml.nvmlDeviceGetMemoryInfo(handle)
            free_bytes = info.free
            logger.debug(f"Free VRAM: {free_bytes / 1024 / 1024 / 1024:.2f} GB")
            return free_bytes
        except pynvml.NVMLError as e:
            logger.error(f"Error querying VRAM: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error querying VRAM: {e}")
            return None

    def can_run_vision_model(self) -> bool:
        """
        Проверить, можно ли запускать визуальную модель.

        Возвращает True, если свободной VRAM достаточно (>4GB по умолчанию).

        Returns:
            True если VRAM доступна, False если недостаточно или NVML недоступен.
        """
        free_vram = self.get_free_vram_bytes()

        if free_vram is None:
            # NVML недоступен - считаем что запускать нельзя
            logger.warning("VRAM check failed (NVML unavailable). Denying VLM launch.")
            return False

        if free_vram < self.vram_threshold_bytes:
            free_gb = free_vram / 1024 / 1024 / 1024
            threshold_gb = self.vram_threshold_bytes / 1024 / 1024 / 1024
            logger.warning(
                f"Insufficient VRAM: {free_gb:.2f}GB < {threshold_gb:.2f}GB. "
                "Denying VLM launch."
            )
            return False

        free_gb = free_vram / 1024 / 1024 / 1024
        logger.debug(f"VRAM check passed: {free_gb:.2f}GB available.")
        return True
    
    def check_vram_availability(self, threshold_mb: int = 4096) -> bool:
        """
        Check if specified amount of VRAM is available.
        
        Args:
            threshold_mb: Minimum free VRAM in MB.
        
        Returns:
            True if VRAM is available, False otherwise.
        """
        free_vram = self.get_free_vram_bytes()
        
        if free_vram is None:
            return False
        
        threshold_bytes = threshold_mb * 1024 * 1024
        return free_vram >= threshold_bytes

    def is_blacklisted_process_running(self) -> bool:
        """
        Проверить, запущен ли какой-либо процесс из черного списка.

        Returns:
            True если найден процесс из черного списка.
        """
        for proc in psutil.process_iter(['name']):
            try:
                proc_name = proc.info['name'].lower() if proc.info['name'] else ""
                if proc_name in self.PROCESS_BLACKLIST:
                    logger.warning(f"Blacklisted process detected: {proc_name}")
                    return True
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue

        return False

    def is_user_active(self) -> bool:
        """
        Проверить, активен ли пользователь (не запущена ли игра).

        Проверяет наличие процессов из черного списка.

        Returns:
            True если пользователь активен (игры не запущены), False если игра запущена.
        """
        if self.is_blacklisted_process_running():
            logger.info("User activity check failed: game detected.")
            return False

        logger.debug("User activity check passed: no games detected.")
        return True

    def is_safe_to_run(self) -> bool:
        """
        Комплексная проверка безопасности запуска тяжелых вычислений.

        Проверяет и VRAM, и активность пользователя.

        Returns:
            True если безопасно запускать VLM, False если нет.
        """
        vram_ok = self.can_run_vision_model()
        user_ok = self.is_user_active()

        if not vram_ok:
            logger.info("SystemGuard: VRAM check failed.")
        if not user_ok:
            logger.info("SystemGuard: User activity check failed.")

        safe = vram_ok and user_ok
        logger.debug(f"SystemGuard safety check: {'PASSED' if safe else 'FAILED'}")
        return safe

    def shutdown(self) -> None:
        """
        Корректное завершение работы с NVML.
        """
        if self.nvml_initialized and pynvml is not None:
            try:
                pynvml.nvmlShutdown()
                self.nvml_initialized = False
                logger.info("NVML shutdown complete.")
            except pynvml.NVMLError as e:
                logger.warning(f"Error shutting down NVML: {e}")

    def __del__(self):
        """Деструктор для гарантированного освобождения ресурсов."""
        self.shutdown()
