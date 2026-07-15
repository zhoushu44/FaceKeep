import asyncio
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
import tempfile
import unittest

from fastapi import UploadFile

import api


class UploadConcurrencyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_paths = (
            api.STORAGE_DIR,
            api.CHUNKS_DIR,
            api.FILES_DIR,
            api.TASKS_DIR,
            api.BACKUPS_DIR,
            api.META_FILE,
        )
        storage = Path(self.temp_dir.name) / "uploads"
        api.STORAGE_DIR = storage
        api.CHUNKS_DIR = storage / "chunks"
        api.FILES_DIR = storage / "files"
        api.TASKS_DIR = storage / "tasks"
        api.BACKUPS_DIR = storage / "backups"
        api.META_FILE = storage / "metadata.json"
        api.ensure_storage()

    def tearDown(self) -> None:
        (
            api.STORAGE_DIR,
            api.CHUNKS_DIR,
            api.FILES_DIR,
            api.TASKS_DIR,
            api.BACKUPS_DIR,
            api.META_FILE,
        ) = self.original_paths
        self.temp_dir.cleanup()

    @staticmethod
    def upload_one(index: int) -> tuple[str, str]:
        content = f"image-{index}".encode()
        session = api.create_upload_session(
            api.UploadSessionRequest(
                fileName=f"image-{index}.png",
                fileSize=len(content),
                fileType="image/png",
                fingerprint=f"fingerprint-{index}",
                totalChunks=1,
            )
        )
        upload_id = session["uploadId"]
        asyncio.run(
            api.upload_chunk(
                uploadId=upload_id,
                chunkIndex=0,
                fingerprint=f"fingerprint-{index}",
                chunk=UploadFile(file=BytesIO(content), filename=f"image-{index}.png"),
            )
        )
        completed = api.complete_upload(api.CompleteUploadRequest(uploadId=upload_id))
        retried = api.complete_upload(api.CompleteUploadRequest(uploadId=upload_id))
        return completed["file"]["id"], retried["file"]["id"]

    def test_parallel_uploads_preserve_every_file_and_allow_retry(self) -> None:
        upload_count = 12
        with ThreadPoolExecutor(max_workers=6) as executor:
            results = list(executor.map(self.upload_one, range(upload_count)))

        self.assertTrue(all(file_id == retried_id for file_id, retried_id in results))
        meta = api.load_meta()
        self.assertEqual(len(meta["files"]), upload_count)
        self.assertEqual(len({item["id"] for item in meta["files"]}), upload_count)
        self.assertTrue(all(Path(item["path"]).exists() for item in meta["files"]))


if __name__ == "__main__":
    unittest.main()
