-- stream_quotes.lua — QLua‑скрипт для QUIK, отправляющий котировки в локальный TCP
local json   = require("json")
local socket = require("socket")

-- ====== настройки ======
local HOST, PORT = "127.0.0.1", 34130  -- порт должен совпадать с settings.TCP_PORT в backend/app/settings.py
local SCRIPT_DIR = getScriptPath()
local FUT_POOL_FILE = SCRIPT_DIR .. "/../data/futures_pool.txt"
local TICS_FILE    = SCRIPT_DIR .. "/Data250818.lua"
local PERIOD_MS = 1000 -- частота отправки (мс)
-- ========================

-- Загружаем таблицу тикеров из Data250818.lua (ожидается глобальная переменная Tic)
local function load_tic()
  local f, err = loadfile(TICS_FILE)
  if not f then
    message("Не удалось загрузить " .. TICS_FILE .. ": " .. tostring(err))
    return {}
  end
  f() -- загружает таблицу Tic в глобальную область
  if type(Tic) ~= "table" then
    message("В " .. TICS_FILE .. " нет таблицы Tic")
    return {}
  end
  return Tic
end

-- Читаем список фьючерсов из текстового файла (по одному SECID в строке, без #)
local function read_fut_pool()
  local set = {}
  local fh = io.open(FUT_POOL_FILE, "r")
  if not fh then return set end
  for line in fh:lines() do
    local s = line:gsub("\r", ""):gsub("\n", "")
    if s ~= "" and s:sub(1,1) ~= "#" then
      set[s] = true
    end
  end
  fh:close()
  return set
end

-- Получаем последнюю цену
local function get_last(class, sec)
  local p = getParamEx(class, sec, "LAST")
  if p and p.param_value ~= nil and p.param_value ~= "" then
    return tonumber(p.param_value) or 0
  end
  return 0
end

-- Габариты: размер лота, гарантийное обеспечение и дней до экспирации
local function get_lot_size(class, sec)
  local p = getParamEx(class, sec, "LOTSIZE")
  return (p and p.param_value ~= "") and tonumber(p.param_value) or nil
end

local function get_go_contract(class, sec)
  local p = getParamEx(class, sec, "BUYDEPO")
  return (p and p.param_value ~= "") and tonumber(p.param_value) or nil
end

local function get_days_to_mat_date(class, sec)
  local p = getParamEx(class, sec, "DAYS_TO_MAT_DATE")
  return (p and p.param_value ~= "") and tonumber(p.param_value) or nil
end

local conn
local fut_pool = {}
local tic_tbl  = {}

function OnInit()
  tic_tbl  = load_tic()
  fut_pool = read_fut_pool()
  conn = socket.tcp()
  conn:settimeout(0)
  local ok, err = conn:connect(HOST, PORT)
  if not ok then
    message("TCP connect error: " .. tostring(err))
  else
    message("stream_quotes.lua стартовал, порт " .. tostring(PORT))
  end
end

-- Сборка массива котировок и метаданных
local function build_payload()
  local now = os.time()
  local out = {}
  for _, row in ipairs(tic_tbl) do
    local name = row.name
    local f1, f2 = row.f1, row.f2
    local ddiv = row.ddiv
    local divr = tonumber(row.divr)
    local utv  = tonumber(row.utv)

    -- Акция (спот)
    if name then
      local s_last = get_last("TQBR", name)
      table.insert(out, {
        class="TQBR", sec=name, last=s_last, ts=now,
        name=name, ddiv=ddiv, divr=divr, utv=utv
      })
    end

    -- Фьючерсы из пула
    local function push_fut(sec)
      if not fut_pool[sec] then return end
      local last = get_last("SPBFUT", sec)
      local lot  = get_lot_size("SPBFUT", sec)
      local go   = get_go_contract("SPBFUT", sec)
      local d2m  = get_days_to_mat_date("SPBFUT", sec)
      table.insert(out, {
        class="SPBFUT", sec=sec, last=last, ts=now,
        name=name, ddiv=ddiv, divr=divr, utv=utv,
        lot_size=lot, go_contract=go, days_to_mat_date=d2m
      })
    end

    if f1 then push_fut(f1) end
    if f2 then push_fut(f2) end
  end
  return out
end

function main()
  while true do
    if conn then
      local payload = build_payload()
      conn:send(json.encode(payload) .. "\n")
    end
    sleep(PERIOD_MS)
  end
end

function OnStop()
  if conn then
    conn:close()
    conn = nil
  end
  message("stream_quotes.lua остановлен")
end
