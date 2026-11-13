import json
import os
import urllib.request
from datetime import date, timedelta

URLS = {
    "market": "https://gapi-ext.innodealing.com/dm-mcp-service/publicapi/mcp/v1/bond-market/",
    "primary": "https://gapi-ext.innodealing.com/dm-mcp-service/publicapi/mcp/v1/bond-primary/",
    "money": "https://gapi-ext.innodealing.com/dm-mcp-service/publicapi/mcp/v1/money-market/",
}


def dm_call(service, tool_name, params):
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": {"params": params},
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

    # 读取 SSE 返回中的最后一条非空 data 行
    lines = [
        line[6:].strip()
        for line in raw.splitlines()
        if line.startswith("data: ") and line[6:].strip()
    ]

    if not lines:
        raise RuntimeError(f"DM 返回为空：{raw[:500]}")

    result = json.loads(lines[-1])["result"]
    text = result["content"][0]["text"].strip()

    if not text:
        raise RuntimeError(f"DM 返回内容为空：{raw[:500]}")

    # DM 偶尔会拼接多段 JSON；只读取第一段完整 JSON
    json_start = min(
    position
    for position in (text.find("{"), text.find("["))
    if position >= 0
)

    body = json.JSONDecoder().raw_decode(text[json_start:])[0]

    if not isinstance(body, dict) or "data" not in body:
        raise RuntimeError(f"DM 返回无 data 字段：{body}")

    return body["data"]


today = date.today()
week_start = today - timedelta(days=6)

# 国债 10Y 近三个月收益率曲线
curve_rows = []
cursor = today - timedelta(days=89)

while cursor <= today:
    end_date = min(cursor + timedelta(days=29), today)

    curve_rows += dm_call(
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

    cursor = end_date + timedelta(days=1)

ten_year_map = {
    row["valuation_date"]: row.get("yield")
    for row in curve_rows
    if str(row.get("curve_term")) in ("10", "10.0")
}

ten_year_curve = [
    {"date": date_value, "yield": ten_year_map[date_value]}
    for date_value in sorted(ten_year_map)
]

# 国债一级发行
primary_rows = dm_call(
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

raw_issues = primary_rows[0].get("list", []) if primary_rows else []
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
            "code": row.get("security_id"),
            "tenor": row.get("bond_issue_tenor"),
            # DM 原始金额按万元处理，转换为亿元
            "amount": (row.get("actu_issue_amount") or 0) / 10000,
            "yield": yield_value,
            "yield_label": yield_label,
            "multiple": row.get("compliant_subscription_mult"),
        }
    )

treasury_issues.sort(
    key=lambda item: item.get("date") or "",
    reverse=True,
)

# 政府债缴款
government_rows = dm_call(
    "money",
    "fund_calendar",
    {
        "user_message": "查询近一周政府债缴款。",
        "start_date": week_start.isoformat(),
        "end_date": today.isoformat(),
        "data_category": 4,
    },
)

government_payments = [
    {
        "date": row.get("data_date"),
        "net": row.get("gov_net_payment"),
    }
    for row in government_rows
]

output = {
    "as_of": today.isoformat(),
    "ten_year_yield_curve": ten_year_curve,
    "treasury_issues": treasury_issues,
    "government_payments": government_payments,
}

with open("data.json", "w", encoding="utf-8") as file:
    json.dump(output, file, ensure_ascii=False)
