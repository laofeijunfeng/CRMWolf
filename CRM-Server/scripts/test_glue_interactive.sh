#!/bin/bash
# Glue 层交互式测试脚本
# 使用方法: ./scripts/test_glue_interactive.sh

BASE_URL="http://localhost:8000/glue/v1"
TENANT="default"
USER_ID=1
MSG_COUNTER=1

echo "========================================"
echo "  Glue 层交互式测试"
echo "========================================"
echo ""

send_message() {
    local text="$1"
    local msg_id="msg_$(date +%s)_$MSG_COUNTER"
    MSG_COUNTER=$((MSG_COUNTER + 1))

    echo ">>> 发送: $text"
    echo ""

    response=$(curl -s -X POST "$BASE_URL/inbound" \
        -H "Content-Type: application/json" \
        -H "x-glue-channel: test" \
        -d "{\"channel_user_id\":\"test_user\",\"message_id\":\"$msg_id\",\"text\":\"$text\",\"timestamp\":$(date +%s),\"crm_user_id_override\":$USER_ID}")

    echo "<<< 响应:"
    echo "$response" | python3 -m json.tool 2>/dev/null || echo "$response"
    echo ""
}

check_session() {
    echo ">>> 查看 Session 状态"
    echo ""

    response=$(curl -s "$BASE_URL/sessions/$TENANT/$USER_ID")
    echo "$response" | python3 -m json.tool 2>/dev/null || echo "$response"
    echo ""
}

clear_session() {
    echo ">>> 清除 Session"
    curl -s -X DELETE "$BASE_URL/sessions/$TENANT/$USER_ID"
    echo ""
}

echo "可用命令:"
echo "  send <文本>    - 发送消息"
echo "  session        - 查看当前 Session"
echo "  clear          - 清除 Session"
echo "  quit           - 退出"
echo ""

while true; do
    read -p "glue> " cmd arg

    case $cmd in
        send)
            if [ -n "$arg" ]; then
                send_message "$arg"
            else
                echo "请输入消息内容，如: send 给#456加跟进"
            fi
            ;;
        session)
            check_session
            ;;
        clear)
            clear_session
            ;;
        quit|exit)
            echo "退出测试"
            break
            ;;
        *)
            if [ -n "$cmd" ]; then
                send_message "$cmd $arg"
            fi
            ;;
    esac
done