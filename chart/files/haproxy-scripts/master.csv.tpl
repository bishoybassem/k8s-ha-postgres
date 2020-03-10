{{ with $master := key "service/postgres/master" | parseJSON -}}
{{ $master.node }},{{ $master.host }}
{{ end }}