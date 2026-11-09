# 0012. 手機上鎖住畫面縮放

## 決定

在手機上鎖住縮放，三種情況分開擋：

- 雙指縮放：viewport 設 `maximum-scale=1`、`user-scalable=no`（`app/layout.tsx`）。
- 雙擊放大：根元素 `touch-action: manipulation`（`shared/ui/styles/base.css`）。
- 點輸入框自動放大：觸控裝置上輸入框字級至少 16px（`--fs-input-touch`）。viewport 已經擋住這種情況，
  但 iOS 的 Safari 分頁會忽略 `user-scalable`，字級是不依賴 viewport 的保底。

不用 JS 攔 `gesturestart`／`touchmove` 去擋 iOS Safari 分頁裡的雙指縮放。

## 為什麼

這個模板的前端要在手機上盡量像原生 App。可以縮放時，雙指、雙擊或點輸入框都可能讓畫面放大，
固定的標題列、底部導覽與對話框跟著跑掉，使用者還得自己縮回來。原生 App 不提供縮放，改由系統字級設定把文字放大。

主流建議是不要鎖縮放：WCAG 1.4.4 要求文字能放大到 200%，Lighthouse 也會把 `user-scalable=no` 與
`maximum-scale` 小於 5 標成無障礙問題。這裡為了接近原生 App 的手感而偏離：加到主畫面以全螢幕開啟、或在 Android 上，
畫面都不會縮放。

不用 JS 攔截，是因為它容易誤擋捲動，iOS 改版也可能失效。

## 代價

- iOS Safari 分頁裡仍可雙指縮放，這是瀏覽器刻意保留的，不另外處理。
- 視力不好的人不能用縮放放大畫面，Lighthouse 的無障礙分數會被扣。Android Chrome 會依系統字級放大文字
  （字級都用 `rem`），iOS 沒有跟隨「動態字體」，要用 `font: -apple-system-body` 另外接。

## 什麼時候重新檢討

專案的使用者包含需要放大畫面的族群、或要符合無障礙規範（例如公部門）時，拿掉 viewport 的
`maximum-scale` 與 `user-scalable` 恢復縮放；`touch-action` 與 16px 字級可以保留。
