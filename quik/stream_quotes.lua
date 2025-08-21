-- stream_quotes.lua — QLua-скрипт для QUIK
return 0
end


local function get_lot_size(class, sec)
local p = getParamEx(class, sec, "LOTSIZE"); if p and p.param_value ~= "" then return tonumber(p.param_value) end; return nil
end


local function get_go_contract(class, sec)
-- BUYDEPO/SELLDEPO часто равны ГО
local p = getParamEx(class, sec, "BUYDEPO"); if p and p.param_value ~= "" then return tonumber(p.param_value) end; return nil
end


local function get_days_to_mat_date(class, sec)
local p = getParamEx(class, sec, "DAYS_TO_MAT_DATE"); if p and p.param_value ~= "" then return tonumber(p.param_value) end; return nil
end


local conn
local fut_pool = {}
local tic_tbl = {}


function OnInit()
tic_tbl = load_tic()
fut_pool = read_fut_pool()
conn = socket.tcp(); conn:settimeout(0)
local ok, err = conn:connect(HOST, PORT)
if not ok then message("TCP connect error: " .. tostring(err)) end
message("stream_quotes.lua стартовал")
end


local function build_payload()
local now = os.time()
local out = {}


-- Пройдём по Tic и возьмём только те фьючерсы, что в пуле
for _, row in ipairs(tic_tbl) do
local name = row.name
local f1, f2 = row.f1, row.f2
local ddiv = row.ddiv
local divr = tonumber(row.divr)
local utv = tonumber(row.utv)


-- Акция (спот)
if name then
local s_last = get_last("TQBR", name)
table.insert(out, {class="TQBR", sec=name, last=s_last, ts=now, name=name, ddiv=ddiv, divr=divr, utv=utv})
end


-- Фьючерсы из пула
local function push_fut(sec)
if not fut_pool[sec] then return end
local last = get_last("SPBFUT", sec)
local lot = get_lot_size("SPBFUT", sec)
local go = get_go_contract("SPBFUT", sec)
local d2m = get_days_to_mat_date("SPBFUT", sec)
table.insert(out, {class="SPBFUT", sec=sec, last=last, ts=now, name=name, ddiv=ddiv, divr=divr, utv=utv, lot_size=lot, go_contract=go, days_to_mat_date=d2m})
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
local line = json.encode(payload) .. "\n"
conn:send(line)
end
sleep(PERIOD_MS)
end
end


function OnStop()
if conn then conn:close(); conn = nil end
message("stream_quotes.lua остановлен")
end