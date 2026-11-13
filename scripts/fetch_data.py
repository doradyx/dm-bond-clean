import json
import os
import urllib.request
from datetime import date, timedelta

URLS = {
    "market": "https://gapi-ext.innodealing.com/dm-mcp-service/publicapi/mcp/v1/bond-market/",
    "primary": "https://gapi-ext.innodealing.com/dm-mcp-service/publicapi/mcp/v1/bond-primary/",
    "money": "https://gapi-ext.innodealing.com/dm-mcp-service/publicapi/mcp/v1/money-market/",
}


def dm_call(service, tool_name, arguments):
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": tool_name,
            # DM MCP 要求参数直接写入 arguments，不能包一层 params
            "arguments": arguments,
        },
    }

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "x-app-key": os.environ["DM_APP_KEY"],
        "x-app-secret": os.environ["DM_APP_SECRET"],
    }

    request = urllib.request.Request(
        URLS[service],
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        raw = response.read().decode("utf-8")

    for line in raw.splitlines():
        if not line.startswith("data: "):
            continue

        try:
            event = json.loads(line[6:].strip())
        except json.JSONDecodeError:
            continue

        result = event.get("result", {})

        if result.get("isError"):
            content = result.get("content", [])
            message = content[0].get("text", "DM 返回未知错误") if content else "DM 返回未知错误"
            raise RuntimeError(message)

        content = result.get("content", [])
        if not content:
            continue

        text = content[0].get("text", "").strip()
        if not text:
            continue

        # 正常情况下 text 是 {"data": ...}；兼容可能附带的文字前缀
        json_start = text.find("{")
        if json_start < 0:
            continue

        try:
            body = json.JSONDecoder().raw_decode(text[json_start:])[0]
        except json.JSONDecodeError:
            continue

        if isinstance(body, dict) and "data" in body:
            return body["data"]

    raise RuntimeError("DM 未返回可用数据：" + raw[:1000])


today = date.today()
week_start = today - timedelta(days=6)

# 一、近三个月：中债国债 10Y 收益率曲线
curve_rows = []
cursor = today - timedelta(days=89)

while cursor <= today:
    end_date = min(cursor + timedelta(days=29), today)

    result = dm_call(
        "market",
        "bond_yield_curve",
        {
            "user_message": "查询中债国债10年期近三个月收益率曲线。",
            "curve_name": "中债国债收益率曲线",
            "curve_term_list": ["10"],
            "curve_type": 1,
            "data_source": 18,
            "start_date": cursor.isoformat(),
            "end_date": end_date.isoformat(),
        },
    )

    if isinstance(result, list):
        curve_rows.extend(result)

    cursor = end_date + timedelta(days=1)

ten_year_map = {
    row.get("valuation_date"): row.get("yield")
    for row in curve_rows
    if row.get("valuation_date")
    and str(row.get("curve_term")) in ("10", "10.0")
    and row.get("yield") is not None
}

ten_year_curve = [
    {"date": date_value, "yield": ten_year_map[date_value]}
    for date_value in sorted(ten_year_map)
]

# 二、近一周：国债一级发行
primary_result = dm_call(
    "primary",
    "bond_primary_data",
    {
        "user_message": "查询近一周国债一级发行。",
        "start_date": week_start.isoformat(),
        "end_date": today.isoformat(),
        "bond_category": 2,
        "limit": 200,
    },
)

if isinstance(primary_result, list) and primary_result:
    raw_issues = primary_result[0].get("list", [])
else:
    raw_issues = []

treasury_issues = []

for row in raw_issues:
    if row.get("bond_type_desc") != "国债":
        continue

    yield_value = row.get("issue_yield")
    yield_label = "发行收益率"

    if yield_value is None:
        yield_value = row.get("comprehensive_yield")
        yield_label = "综合收益率"

    if yield_value is None:
        yield_value = row.get("weighted_rate")
        yield_label = "加权收益率"

    if yield_value is None:
        yield_value = row.get("marginal_rate")
        yield_label = "边际收益率"

    treasury_issues.append(
        {
            "date": row.get("subscribe_date"),
            # 固定使用券号，例如 260020.IB
            "code": row.get("security_id"),
            # 原始期限直接展示，不在页面再拼 Y
            "tenor": row.get("bond_issue_tenor"),
            # DM 原始金额单位为万元，换算为亿元
            "amount": round((row.get("actu_issue_amount") or 0) / 10000, 2),
            "yield": yield_value,
            "yield_label": yield_label,
            "multiple": row.get("compliant_subscription_mult"),
        }
    )

treasury_issues.sort(
    key=lambda item: item.get("date") or "",
    reverse=True,
)

# 三、近一周：仅保留政府债缴款，不展示公开市场净投放
government_result = dm_call(
    "money",
    "fund_calendar",
    {
        "user_message": "查询近一周政府债缴款。",
        "start_date": week_start.isoformat(),
        "end_date": today.isoformat(),
        "data_category": 4,
    },
)

government_payments = []

if isinstance(government_result, list):
    for row in government_result:
        government_payments.append(
            {
                "date": row.get("data_date"),
                "net": row.get("gov_net_payment"),
            }
        )

government_payments.sort(
    key=lambda item: item.get("date") or "",
    reverse=True,
)

output = {
    "as_of": today.isoformat(),
    "ten_year_yield_curve": ten_year_curve,
    "treasury_issues": treasury_issues,
    "government_payments": government_payments,
}

with open("data.json", "w", encoding="utf-8") as file:
    json.dump(output, file, ensure_ascii=False, indent=2)
