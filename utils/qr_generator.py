"""QR code generation utility for restaurant tables."""
import logging
from pathlib import Path

import qrcode
from qrcode.constants import ERROR_CORRECT_M

from config.settings import settings

logger = logging.getLogger(__name__)


class QRCodeGenerator:
    """Generates QR codes for restaurant table links."""

    def __init__(self, bot_username: str, output_dir: str = "qr_codes"):
        """Initialize the QR code generator.
        
        Args:
            bot_username: The Telegram bot username (without @).
            output_dir: Directory to save QR code images.
        """
        self._bot_username = bot_username
        self._output_dir = Path(output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)

    def generate_table_qr(self, table_number: int) -> str:
        """Generate a QR code for a specific table.
        
        Args:
            table_number: The restaurant table number.
            
        Returns:
            Path to the generated QR code image file.
        """
        url = f"https://t.me/{self._bot_username}?start=table_{table_number}"
        
        qr = qrcode.QRCode(
            version=1,
            error_correction=ERROR_CORRECT_M,
            box_size=10,
            border=4,
        )
        qr.add_data(url)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        filepath = self._output_dir / f"table_{table_number}_qr.png"
        with open(str(filepath), "wb") as f:
            img.save(f)
        
        logger.info(f"QR code for table {table_number} saved to {filepath}")
        return str(filepath)

    def generate_all_table_qrs(self, total_tables: int) -> list[str]:
        """Generate QR codes for all tables.
        
        Args:
            total_tables: Total number of tables.
            
        Returns:
            List of file paths to generated QR code images.
        """
        filepaths = []
        for table_number in range(1, total_tables + 1):
            filepath = self.generate_table_qr(table_number)
            filepaths.append(filepath)
        logger.info(f"Generated {len(filepaths)} QR codes for tables.")
        return filepaths


def main():
    """CLI entry point for generating QR codes."""
    import argparse
    
    from utils.logger import setup_logging
    
    parser = argparse.ArgumentParser(description="Generate QR codes for restaurant tables.")
    parser.add_argument(
        "--username",
        default="Tokio_bar_bot",
        help="Bot username (default: Tokio_bar_bot)",
    )
    parser.add_argument(
        "--tables",
        type=int,
        default=settings.total_tables,
        help=f"Number of tables (default: {settings.total_tables})",
    )
    parser.add_argument(
        "--output",
        default="qr_codes",
        help="Output directory (default: qr_codes)",
    )
    
    args = parser.parse_args()
    
    setup_logging()
    generator = QRCodeGenerator(args.username, args.output)
    generator.generate_all_table_qrs(args.tables)


if __name__ == "__main__":
    main()