# 台灣高鐵網路訂票（IRS）流程與真實欄位參數整理

本文件整理自實際擷取的高鐵官網（irs.thsrc.com.tw）HTML 原始碼，記錄「訂票」「查詢訂位」「取消訂位」三條完整流程中，每一步真正送出的表單欄位名稱與合法值。所有欄位名稱與值都是從真實頁面逐一比對出來的，不是猜測。

---

## 0. 通用架構備忘（Wicket 框架的關鍵行為）

高鐵訂票系統使用 Apache Wicket 框架，跟一般表單串接不一樣，有幾個地方特別容易踩雷：

1. **每個 `<form>` 都帶一個隱藏版本追蹤欄位**，格式是 `{表單ID}:hf:0`（例如 `BookingS1Form:hf:0`、`HistoryForm:hf:0`）。這個欄位沒有跟著送出，Wicket 極可能直接判定「頁面已過期」而拒絕請求。
2. **除了 `hf:0`，同一個 `<form>` 裡通常還有其他隱藏欄位**（例如 `portalTag`、`diffOver`、`isEarlyBirdRegister`），這些也必須原封不動一起送出。
3. **每一步的表單 `action` 網址都不同**，而且是動態產生的（帶 `wicket:interface=:N:...`），不能寫死，一定要從「上一步回傳的 HTML」裡重新解析 `<form action="...">`。
4. **正確做法**：每次送出表單後，都要重新解析回傳的 HTML，抓出新的 `action` 網址 + 新的所有 `hidden` 欄位，供下一步使用（本專案程式碼裡的 `_extract_form_context()` 做的就是這件事）。
5. **並非每個「按鈕」都是表單提交**：例如「取消訂位」那個連結其實是 Wicket 的 `ILinkListener`（GET 連結），不是 `IFormSubmitListener`（POST 表單提交），兩者處理方式不同（見第 5 節）。

---

## 1. 訂票流程（一般訂票）

### 步驟 1：首頁查詢表單（`BookingS1Form`）

| 欄位名稱 | 說明 | 合法值 |
|---|---|---|
| `tripCon:typesoftrip` | 單程/來回 | `0`=單程　`1`=去回程 |
| `bookingMethod` | 搜尋方式 | `radio31`=依時間查詢　`radio33`=依車次查詢 |
| `selectStartStation` | 出發站 | `1`~`12`（見下方車站對照表，**不是**四碼車站代碼）|
| `selectDestinationStation` | 到達站 | 同上 |
| `toTimeInputField` | 出發日期 | `YYYY/MM/DD`，例如 `2026/07/26` |
| `toTimeTable` | 出發時間 | 見下方時間對照表（**不補零、英文大寫**）|
| `toTrainIDInputField` | 依車次查詢時的車次號碼 | 4 碼數字字串 |
| `backTimeInputField` / `backTimeTable` / `backTrainIDInputField` | 來回程對應欄位 | 同上，僅來回程需要 |
| `ticketPanel:rows:0:ticketAmount` | 全票數量 | `{數量}F`，例如 `1F` |
| `ticketPanel:rows:1:ticketAmount` | 孩童票(6-11) | `{數量}H` |
| `ticketPanel:rows:2:ticketAmount` | 愛心票 | `{數量}W` |
| `ticketPanel:rows:3:ticketAmount` | 敬老票(65+) | `{數量}E` |
| `ticketPanel:rows:4:ticketAmount` | 大學生票 | `{數量}P` |
| `ticketPanel:rows:5:ticketAmount` | 少年票(12-18) | `{數量}T` |
| `trainCon:trainRadioGroup` | **車廂別** | `0`=標準車廂　`1`=商務車廂 |
| `seatCon:seatRadioGroup` | **座位偏好** | `0`=無偏好　`1`=靠窗優先　`2`=靠走道優先 |
| `trainTypeContainer:typesoftrain` | 車次需求 | `0`=所有車次　`1`=限定早鳥優惠車次　`2`=無需早鳥(全票以原價計) |
| `homeCaptcha:securityCode` | 驗證碼 | 使用者輸入的文字 |

⚠️ **常見誤區**：`trainCon:trainRadioGroup`（車廂別）跟 `seatCon:seatRadioGroup`（座位偏好）欄位名稱長得像，容易搞混塞反。票種數量欄位**一定要帶字母後綴**（`1F` 而非 `1`），少了後綴或用純數字送出，會被高鐵拒絕或造成後續解析炸掉。

**車站對照表**（`selectStartStation` / `selectDestinationStation` 共用）：

| 值 | 站名 | 值 | 站名 |
|---|---|---|---|
| 1 | 南港 | 7 | 台中 |
| 2 | 台北 | 8 | 彰化 |
| 3 | 板橋 | 9 | 雲林 |
| 4 | 桃園 | 10 | 嘉義 |
| 5 | 新竹 | 11 | 台南 |
| 6 | 苗栗 | 12 | 左營 |

**時間對照表**（`toTimeTable` / `backTimeTable` 共用，節錄）：

`1201A`=00:00　`1230A`=00:30　`500A`=05:00　`530A`=05:30　`600A`=06:00 … `1130A`=11:30　`1200N`=12:00（**注意中午是 N 不是 P**）　`1230P`=12:30　`100P`=13:00 … `1130P`=23:30

（完整清單見專案 `thsr.py` 裡的 `TIME_TABLE` 常數）

---

### 步驟 2：車次查詢結果頁

查詢結果頁把每一班車的資料，直接放在 `<input type="radio">` 本身的自訂屬性上，不需要（也不建議）用文字比對子節點抓取：

```html
<input name="TrainQueryDataViewPanel:TrainGroup"
       type="radio" value="radio22"
       QueryCode="1602"
       QueryDeparture="06:53"
       QueryArrival="07:10"
       QueryDepartureDate="07/28"
       QueryEstimatedTime="0:17" />
```

| 屬性 | 說明 |
|---|---|
| `name` | 表單欄位名稱，固定是 `TrainQueryDataViewPanel:TrainGroup`（去回程的回程可能是 `TrainQueryDataViewPanel2:TrainGroup`）|
| `value` | 選擇該車次要送出的值（例如 `radio22`），**這是下一步 `select-train` 要送出的值** |
| `QueryCode` | 車次號碼 |
| `QueryDeparture` / `QueryArrival` | 出發／到達時刻 |
| `QueryDepartureDate` | 出發日期 |
| `QueryEstimatedTime` | 行車時間 |

優惠資訊（早鳥折扣等）在同一個 `<label class="result-item">` 底下的 `.discount` 元素文字。

---

### 步驟 3：選擇車次後的取票人／乘客資訊頁（`BookingS3FormSP`）

| 欄位名稱 | 說明 | 合法值 |
|---|---|---|
| `idInputRadio` | 取票識別碼的證件類型 | `0`=身分證字號　`1`=護照/居留證/入出境許可證號 |
| `dummyId` | **取票識別碼**（取票時用，通常填身分證字號） | 字串 |
| `dummyPhone` | 聯絡電話 | 字串 |
| `email` | 電子郵件（選填） | 字串 |
| `TicketPassengerInfoInputPanel:passengerDataView:{i}:passengerDataView2:passengerDataInputChoice` | 第 i 位乘客的證件類型 | `0`/`1`，同上 |
| `TicketPassengerInfoInputPanel:passengerDataView:{i}:passengerDataView2:passengerDataIdNumber` | **第 i 位乘客的真實身分證字號**（早鳥/記名優惠票種驗證用） | 字串，**i 從 0 起算** |
| `TicketMemberSystemInputPanel:TakerMemberSystemDataView:memberSystemRadioGroup` | 高鐵會員類型 | `radio54`=非會員　`radio56`=TGo會員　`radio59`=企業會員 |
| `agree` | 同意交易約定事項（checkbox） | `on`（必須勾選，否則直接被拒絕）|

⚠️ **這是最容易漏掉、也最容易造成「乘客 1 身分證字號不能為空白」錯誤的一步**：`dummyId`（取票識別碼）跟 `passengerDataIdNumber`（乘客真實身分證字號）是**兩個不同的欄位**，早鳥/記名票種**兩個都要填**，只填 `dummyId` 不夠。

隱藏欄位（自動隨頁面帶出，需原樣送出，不需手動組）：`BookingS3FormSP:hf:0`、`diffOver`、`isSPromotion`、`isEarlyBirdRegister`、`passengerCount`、`memberAct`、`isGoBackM`、`backHome`、`TgoError`、`isMustBeCard`。

---

### 步驟 4：訂位完成頁（顯示訂位代號，尚未付款）

| 選擇器 | 說明 |
|---|---|
| `.pnr-code` | 訂位代號（例如 `03532489`）|
| `.payment-status .status-unpaid` | 付款狀態＋付款期限（裡面多個 `<span>`，期限格式 `MM/DD`）|
| `.seat-label` | 座位（例如 `5車11E`）|
| `[id^='InfoPrice']` 的 `price` 屬性 | 總票價（例如 `price="125"`，比文字解析可靠）|
| `.departure-stn` / `.arrival-stn` | 出發／到達站名 |
| `.date` | 乘車日期（`MM/DD`）|
| `[id^='setTrainCode']` | 車次號碼 |
| `[id^='setTrainDeparture']` / `[id^='setTrainArrival']` | 出發／到達時刻 |

---

## 2. 訂位紀錄查詢流程（管理訂位）

### 步驟 1：查詢表單（`HistoryForm`）

| 欄位名稱 | 說明 | 合法值 |
|---|---|---|
| `typesofid` | 取票識別碼的證件類型（select，`id="idInputRadio"` 但 **`name` 是 `typesofid`**，跟訂票流程的 `idInputRadio` 不同名，要注意）| `0`=身分證字號　`1`=護照/居留證/入出境許可證號 |
| `rocId` | 證件號碼 | 字串 |
| `orderId` | 訂位代號 | 8 碼字串 |
| `divCaptcha:securityCode` | 驗證碼 | 字串 |

驗證碼圖片網址：`wicket:interface=:N:HistoryForm:divCaptcha:passCode::IResourceListener`（跟訂票首頁的驗證碼機制相同，一樣需要動態抓取）。

### 步驟 2：查詢結果頁（`HistoryDetailsForm`）

這一頁本身主要是**顯示**訂位明細（跟訂票完成頁的欄位選擇器完全相同：`.pnr-code`、`.seat-label`、`[id^='setTrainCode']` 等），沒有需要送出的表單資料。頁面上有一個「取消/修改訂位」的下拉選單，裡面「取消訂位」是一個**連結（GET 請求）**：

```html
<a href="/IMINT/?wicket:interface=:N:HistoryDetailsForm:TicketProcessButtonPanel:actionBtns:CancelSeatsButton::ILinkListener">取消訂位</a>
```

⚠️ 這個是 `ILinkListener`，**不是表單提交**，要用 GET 方式直接訪問這個連結（記得從目前頁面動態抓取，因為 `wicket:interface=:N:` 的數字每次不同），才會進到下一步的取消確認頁。

---

## 3. 取消訂位流程

### 步驟 1：取消確認頁（`HistoryDetailsCancelForm`）

顯示要取消的訂位明細（跟前面同樣的選擇器），需要送出：

| 欄位名稱 | 說明 | 合法值 |
|---|---|---|
| `agree` | 「我確定要取消本筆訂位記錄」checkbox | 必須勾選才能繼續 |
| `SubmitButton` | 送出按鈕 | value=`下一步` |

### 步驟 2：取消結果頁（`HistoryDetailsResultForm`）

成功訊息文字為「訂位代號 `{PNR}` 取消訂位成功！」，可用此文字判斷是否取消成功。頁面上「回到首頁」按鈕欄位名稱為 `resultDiv:Button`。

---

## 4. 目前程式（`thsr.py`）已經實作 / 尚未實作的部分

| 功能 | 狀態 |
|---|---|
| 查詢車次、選車次、填資料、完成訂位 | ✅ 已實作且驗證可用（訂位代號 `03532489`、`03533190` 皆為真實成功訂位）|
| 訂位完成頁資訊解析（`BookingResult`） | ✅ 已修正，可正確解析真實頁面 |
| 訂位紀錄查詢（`HistoryForm` → `HistoryDetailsForm`） | ❌ 尚未實作 |
| 取消訂位（`CancelSeatsButton` → `HistoryDetailsCancelForm` → `HistoryDetailsResultForm`） | ❌ 尚未實作 |

有了這份文件的欄位對照，下一步可以直接照著實作「查詢訂位」跟「取消訂位」兩支新的 API 路由，不需要再逐輪用猜的除錯。
