"""文件存储服务：本地存储发票文件，支持团队隔离和路径安全校验。"""

import os
import hashlib
from datetime import datetime


class FileStorageError(Exception):
    """文件存储错误"""
    pass


# 允许的文件扩展名（发票常见格式）
ALLOWED_EXTENSIONS = {
    ".pdf",   # PDF 发票
    ".jpg",   # 图片发票
    ".jpeg",
    ".png",
    ".ofd",   # 电子发票格式
}

# 最大文件大小（10MB）
MAX_FILE_SIZE = 10 * 1024 * 1024


class FileStorageService:
    """发票文件本地存储服务"""

    def __init__(self, base_dir: str = "/app/uploads"):
        """
        Args:
            base_dir: 上传文件基础目录（容器内路径）
        """
        self.base_dir = base_dir

    def _validate_filename(self, filename: str) -> str:
        """校验文件名安全性

        1. 禁止路径穿越（../）
        2. 只允许白名单扩展名
        3. 返回安全的文件名
        """
        # 检查路径穿越
        if ".." in filename or "/" in filename or "\\" in filename:
            raise FileStorageError(f"非法文件名：{filename}")

        # 检查扩展名
        ext = os.path.splitext(filename)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise FileStorageError(
                f"不允许的文件类型：{ext}。允许类型：{', '.join(ALLOWED_EXTENSIONS)}"
            )

        return filename

    def _generate_safe_filename(self, original_filename: str, invoice_id: int) -> str:
        """生成安全的存储文件名

        格式：{invoice_id}_{timestamp}_{hash}.{ext}
        """
        ext = os.path.splitext(original_filename)[1].lower()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        # 用 invoice_id + timestamp 作为 hash 输入，避免文件名冲突
        hash_input = f"{invoice_id}_{timestamp}_{original_filename}"
        hash_suffix = hashlib.md5(hash_input.encode()).hexdigest()[:8]

        return f"{invoice_id}_{timestamp}_{hash_suffix}{ext}"

    def save_invoice_file(
        self,
        team_id: int,
        invoice_id: int,
        filename: str,
        content: bytes,
    ) -> str:
        """保存发票文件

        Args:
            team_id: 团队 ID（用于目录隔离）
            invoice_id: 发票申请 ID
            filename: 原始文件名
            content: 文件内容（bytes）

        Returns:
            文件相对路径（相对于 base_dir），用于存储到数据库

        Raises:
            FileStorageError: 文件名非法或存储失败
        """
        # 校验文件大小
        if len(content) > MAX_FILE_SIZE:
            raise FileStorageError(
                f"文件过大：{len(content)} 字节，最大允许 {MAX_FILE_SIZE} 字节"
            )

        # 校验文件名
        safe_filename = self._validate_filename(filename)
        storage_filename = self._generate_safe_filename(safe_filename, invoice_id)

        # 构建目录路径：{base_dir}/invoices/{team_id}/{invoice_id}/
        dir_path = os.path.join(self.base_dir, "invoices", str(team_id), str(invoice_id))

        # 创建目录（如果不存在）
        os.makedirs(dir_path, exist_ok=True)

        # 写文件
        full_path = os.path.join(dir_path, storage_filename)
        with open(full_path, "wb") as f:
            f.write(content)

        # 返回相对路径
        relative_path = os.path.join("invoices", str(team_id), str(invoice_id), storage_filename)
        return relative_path

    def get_full_path(self, relative_path: str) -> str:
        """获取文件完整路径

        Args:
            relative_path: 数据库存储的相对路径

        Returns:
            完整文件路径
        """
        # 安全校验：确保路径在 base_dir 内
        full_path = os.path.join(self.base_dir, relative_path)
        # 规范化路径，防止路径穿越
        real_path = os.path.realpath(full_path)
        real_base = os.path.realpath(self.base_dir)

        if not real_path.startswith(real_base):
            raise FileStorageError("非法路径：路径超出上传目录范围")

        return full_path

    def file_exists(self, relative_path: str) -> bool:
        """检查文件是否存在"""
        try:
            full_path = self.get_full_path(relative_path)
            return os.path.exists(full_path)
        except FileStorageError:
            return False

    def delete_file(self, relative_path: str) -> bool:
        """删除文件

        Returns:
            True 如果删除成功，False 如果文件不存在
        """
        try:
            full_path = self.get_full_path(relative_path)
            if os.path.exists(full_path):
                os.remove(full_path)
                return True
            return False
        except FileStorageError:
            return False


# 单例实例
file_storage_service = FileStorageService()