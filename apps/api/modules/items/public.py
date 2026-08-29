"""給其他後端 module 使用的公開介面。

**範例模組**的跨模組接縫。目前沒有任何 module 需要它 —— 留著是為了讓「複製 items
當新模組」時這個檔案已經在正確的位置。真的沒有跨模組需求時，新模組不必建這一份：
public entry 要**最小**，見 docs/architecture.md「新增 module」。
"""

from .model import ItemTable

__all__ = ["ItemTable"]
