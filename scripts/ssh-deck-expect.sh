#!/usr/bin/expect -f
# Usage: DECK_PASS=xxx ./scripts/ssh-deck-expect.sh <remote-command>
# Or:    ./scripts/ssh-deck-expect.sh scp <local> <remote>
set timeout 90
set deck_ip [expr {[info exists env(DECK_IP)] ? $env(DECK_IP) : "192.100.254.11"}]
set deck_user "deck"
if {![info exists env(DECK_PASS)]} {
    puts "Set DECK_PASS"
    exit 1
}
set pass $env(DECK_PASS)

if {[lindex $argv 0] eq "scp"} {
    set local [lindex $argv 1]
    set remote [lindex $argv 2]
    spawn scp -o StrictHostKeyChecking=no $local ${deck_user}@${deck_ip}:$remote
} else {
    set cmd [join $argv " "]
    spawn ssh -o StrictHostKeyChecking=no ${deck_user}@${deck_ip} $cmd
}
expect {
    -re "(?i)password:" {
        send "$pass\r"
        exp_continue
    }
    eof
}
catch wait result
exit [lindex $result 3]
