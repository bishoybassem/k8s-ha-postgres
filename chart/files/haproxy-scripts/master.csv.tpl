{{ with $master := key (print (env "CONSUL_KEY_PREFIX") "/master") | parseJSON -}}
{{ range service "postgres" -}}
{{ if eq $master.node .Node -}}
{{ .Node }},{{ .Address }}
{{ end -}}
{{ end -}}
{{ end }}