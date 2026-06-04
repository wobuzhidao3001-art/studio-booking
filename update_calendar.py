with open("/home/admin/studio-booking/templates/dashboard.html", "r") as f:
    content = f.read()

old = "h+='<div style=\"width:4px;height:32px;border-radius:3px;background:'+barColor+';flex-shrink:0\"></div>';"
new = "h+='<div style=\"width:4px;height:48px;border-radius:3px;background:'+barColor+';flex-shrink:0\"></div>';"
content = content.replace(old, new)

old2 = "h+='</div>';"
# Only replace the one immediately after the time display
# Let's use a more specific pattern
idx = content.find("margin-top:1px;\">'+fmtTime(a.start)+' — '+fmtTime(a.end)+'</div>';")
if idx >= 0:
    # Find the next '</div>'; after this
    end_close = content.find("h+='</div>';", idx)
    if end_close >= 0:
        insert_point = end_close + len("h+='</div>';")
        bar_code = "\n                    h+='<div class=\"mini-bar\" style=\"margin-top:4px;\">'+renderMiniBar(a.start,a.end)+'</div><div class=\"t-time-labels\"><span>08:00</span><span>10:00</span><span>12:00</span><span>14:00</span><span>16:00</span><span>18:00</span><span>20:00</span><span>22:00</span></div>';"
        content = content[:insert_point] + bar_code + content[insert_point:]
        print("OK - inserted mini-bar")
    else:
        print("FAIL - end not found")
else:
    print("FAIL - pattern not found")

with open("/home/admin/studio-booking/templates/dashboard.html", "w") as f:
    f.write(content)
