usage: cheri.py [-h] [-u URL] [--chain CHAIN] [--deeping DEEPING] [--delay DELAY]
                [--timeout TIMEOUT] [--threads THREADS] [--output OUTPUT] [--mail MAIL]
                [--custom CUSTOM] [--time-sec-mode] [--tor] [--https-only]
                [--user-agent USER_AGENT] [--subfinder] [--ignore-gapps]
                [--method {GET,POST,PUT,DELETE,PATCH,HEAD,OPTIONS,ALL}] [--skip-pick]
                [--imitation] [--tasker] [--stay] [--find-keys] [--param PARAM]
                [--disable-ssl] [--no-content-limit] [--scilla [SCILLA]]

Gelişmiş Web Tarayıcı - Derin Link & Gizli Endpoint Keşfi

options:
  -h, --help            show this help message and exit
  -u, --url URL         Taranacak hedef URL
  --chain CHAIN         Hedef listesi dosyası (her satırda bir hedef)
  --deeping DEEPING     Maksimum tarama derinliği (varsayılan: 3)
  --delay DELAY         İstekler arası bekleme süresi saniye (varsayılan: 0.05)
  --timeout TIMEOUT     İstek zaman aşımı saniye (varsayılan: 5)
  --threads THREADS     Maksimum eşzamanlı thread (varsayılan: 40)
  --output OUTPUT       URL'ler için çıktı metin dosyası yolu (varsayılan: dosya
                        çıktısı yok)
  --mail MAIL           E-posta adresleri için çıktı dosyası (varsayılan: e-posta
                        dosyası yok)
  --custom CUSTOM       Özel domain filtresi (örn: "api" sadece "api" içeren URL'leri
                        işler)
  --time-sec-mode       Zaman güvenlik modunu etkinleştir (her 1000 linkte 45 saniye
                        duraklama)
  --tor                 İstekler için TOR proxy kullan
  --https-only          Sadece HTTPS URL'lerini tara
  --user-agent USER_AGENT
                        Özel User-Agent string'i
  --subfinder           Alt domain bulmak için subfinder kullan
  --ignore-gapps        Google ile ilgili URL'leri görmezden gel
  --method {GET,POST,PUT,DELETE,PATCH,HEAD,OPTIONS,ALL}
                        Test edilecek HTTP method'u (varsayılan: GET)
  --skip-pick           Resim, CSS, font dosyalarını atla (.css, .jpg, .png, .gif,
                        .woff, vb.)
  --imitation           Her 50 istekte fingerprint ve kullanıcı aracını rastgele
                        değiştir
  --tasker              Endpoint'leri bulduğu diğer sitelere test et
  --stay                Sadece hedef domain'de kal, diğer domain'lere geçme
  --find-keys           API anahtarlarını bul ve ekranda göster (varsayılan: kapalı)
  --param PARAM         Benzersiz parametreleri kaydetmek için dosya yolu (örn:
                        params.txt)
  --disable-ssl         SSL doğrulamasını devre dışı bırak (güvenli değil!)
  --no-content-limit    İçerik boyutu sınırı yok (sınırsız)
  --scilla [SCILLA]     Scilla kullan (report, dns, port, subdomain, dir, sql)


Örnekler:
  cheri -u https://bank.govm
  cheri -u https://bank.gov --output outputs.txt
  cheri --chain targets.txt --output sonuclar.txt
  cheri -u https://bank.gov --custom "api"
  cheri -u https://bank.gov --time-sec-mode
  cheri -u https://bank.gov --tor
  cheri -u https://bank.gov --https-only
  cheri -u https://bank.gov --user-agent "Özel Bot"
  cheri -u https://bank.gov --mail epostalar.txt
  cheri -u https://bank.gov --subfinder
  cheri -u https://bank.gov --ignore-gapps
  cheri -u https://bank.gov --method POST
  cheri -u https://bank.gov --method ALL
  cheri -u https://bank.gov --skip-pick
  cheri -u https://bank.gov --imitation
  cheri -u https://bank.gov --tasker
  cheri -u https://bank.gov --stay
  cheri -u https://bank.gov --find-keys
  cheri -u https://bank.gov --param params.txt
  cheri -u https://bank.gov --disable-ssl
  cheri -u https://bank.gov --scilla
  cheri -u https://bank.gov --scilla=dns
  cheri -u https://bank.gov --scilla=port
  cheri -u https://bank.gov --scilla=subdomain
  cheri -u https://bank.gov --scilla=dir
  cheri -u https://bank.gov --scilla=sql
