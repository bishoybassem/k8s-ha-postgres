{{ range service "postgres" -}}
{{ if eq "Standby" (key (print (env "CONSUL_KEY_PREFIX") "/" .Node "/role")) -}}
{{ .Node }},{{ .Address }}
{{ end -}}
{{ end -}}