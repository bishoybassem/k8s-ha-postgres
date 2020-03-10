{{ with $master := key "service/postgres/master" | parseJSON -}}
{{ range service "postgres" -}}
{{ if ne .Address $master.host -}}
{{ .Node }},{{ .Address }}
{{ end -}}
{{ end -}}
{{ end -}}