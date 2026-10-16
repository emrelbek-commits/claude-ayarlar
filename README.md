# claude-ayarlar

Claude Code için skill koleksiyonu. Tüm skill'ler `.claude/skills/` klasöründe. Bu repoyla açılan her Claude Code oturumunda kendiliğinden yüklenir.

## Skill'ler nasıl çalışır?

Her skill'i iki şekilde kullanabilirsin:

- **Otomatik:** Claude, yaptığın işe uyan skill'i kendisi seçer. Örneğin "bu hatayı düzelt" dersen `systematic-debugging` devreye girer.
- **Elle:** Mesaj kutusuna `/` ve skill adını yaz. Örneğin `/brainstorming` ya da `/caveman`.

Aşağıdaki tablolarda **"Ne zaman devreye girer"** sütunu, skill'in kendiliğinden açıldığı durumları gösteriyor. Elle çağırmak için her zaman `/skill-adı` yazabilirsin.

---

## 1. Planlama ve iş akışı (Superpowers)

Kaynak: [obra/superpowers](https://github.com/obra/superpowers)

| Skill | Ne yapar | Ne zaman devreye girer |
|---|---|---|
| `brainstorming` | Yeni bir şeye başlamadan önce sana sorular sorarak fikri netleştirir, tasarımı yazıya döker | Yeni özellik, sayfa ya da proje istediğinde |
| `writing-plans` | İşi küçük, test edilebilir adımlara bölen bir plan yazar | Gereksinimler belli olup koda geçmeden önce |
| `executing-plans` | Yazılmış planı adım adım uygular | "Planı uygula" dediğinde |
| `subagent-driven-development` | Planı, her adımı ayrı bir yardımcı ajana yaptırarak uygular | Bağımsız adımlardan oluşan büyük planlarda |
| `dispatching-parallel-agents` | Birbirinden bağımsız işleri aynı anda yaptırır | 2 ya da daha fazla bağımsız iş olduğunda |
| `using-git-worktrees` | Çalışmayı ana koddan ayrı bir klasörde yürütür | Büyük bir özelliğe başlarken |
| `finishing-a-development-branch` | İş bitince birleştirme, PR açma ya da bırakma seçeneklerini sunar | Tüm testler geçtikten sonra |
| `using-superpowers` | Claude'a "her işten önce uygun skill'i kontrol et" kuralını verir | Konuşma başlarken |
| `diagnosing-superpowers` | Superpowers ile ilgili bir şey ters gittiğinde nedenini araştırır | "Neden bu kadar uzun sürdü", "skill neden çalışmadı" gibi sorularda |

## 2. Kod kalitesi ve hata ayıklama

| Skill | Kaynak | Ne yapar | Ne zaman devreye girer |
|---|---|---|---|
| `karpathy-guidelines` | Karpathy | Varsayımları açıkça söyle, sade yaz, sadece gerekeni değiştir, sonucu doğrula | Kod yazarken, incelerken, düzenlerken |
| `test-driven-development` | Superpowers | Önce test yazar, sonra kodu | Yeni özellik ya da hata düzeltmesinde, koddan önce |
| `systematic-debugging` | Superpowers | Hatanın kök nedenini adım adım bulur, tahminle düzeltmez | Hata, başarısız test ya da beklenmeyen davranışta |
| `verification-before-completion` | Superpowers | "Bitti" demeden önce komut çalıştırıp kanıt gösterir | İşi tamamlandı ilan etmeden önce |
| `requesting-code-review` | Superpowers | Yapılan işin incelenmesini ister | Büyük bir özellik bitince ya da birleştirmeden önce |
| `receiving-code-review` | Superpowers | Gelen inceleme yorumlarını körü körüne uygulamadan değerlendirir | İnceleme yorumu geldiğinde |
| `investigate-first` | Caveman | Nedeni belirsiz hatalarda önce kanıt toplar, sonra düzeltir | Nedeni bilinmeyen, ara sıra çıkan hatalarda |
| `lean-build` | Caveman | Gereğinden fazla kod yazmayı engeller, işi net bir bitiş noktasıyla yapar | Yeni özellik ya da entegrasyon eklerken |
| `surgical-patch` | Caveman | Hatayı en dar noktada düzeltir, çevresine dokunmaz | Küçük hata düzeltmelerinde |
| `safe-refactor` | Caveman | Davranışı bozmadan kodu yeniden düzenler | Kod temizliği ve yeniden yapılandırmada |
| `migration` | Caveman | Veritabanı, API ya da ayar geçişlerini geri alınabilir şekilde yapar | Şema, veri ya da bağımlılık geçişlerinde |
| `verify-and-stop` | Caveman | Mevcut işin şartları karşıladığını kanıtlar, kapsamı genişletmez | Sadece doğrulama istendiğinde |

> Not: `systematic-debugging` ile `investigate-first`, `verification-before-completion` ile `verify-and-stop` hemen hemen aynı işi yapar. Birini kapatmak Claude'un daha tutarlı davranmasını sağlar.

## 3. Arayüz ve tasarım (UI/UX Pro Max)

Kaynak: [nextlevelbuilder/ui-ux-pro-max-skill](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill)

| Skill | Ne yapar | Ne zaman devreye girer |
|---|---|---|
| `ui-ux-pro-max` | 79 stil, 192 renk paleti, 74 yazı tipi eşleşmesi ve erişilebilirlik kuralları içeren arama aracı | Sayfa, bileşen, renk, yazı tipi ya da düzen kararlarında |
| `ui-styling` | shadcn/ui ve Tailwind ile erişilebilir arayüz bileşenleri kurar | Arayüz kodlarken, karanlık mod, form, tablo gibi bileşenlerde |
| `design-system` | Renk, boşluk ve yazı ölçülerini tek yerde tutan tasarım sistemi kurar | Tasarım sistemi ya da tutarlı stil gerektiğinde |
| `design` | Logo, kurumsal kimlik, ikon, sosyal medya görseli üretir | Logo ya da marka görseli istediğinde. Logo üretimi için ayrıca API anahtarı gerekir |
| `brand` | Marka dili, ton ve görsel kimlik tutarlılığı | Markalı içerik, ton ya da stil rehberi işlerinde |
| `banner-design` | Sosyal medya, reklam ve web sitesi banner'ları | Banner ya da kapak görseli istediğinde |
| `slides` | Grafikli HTML sunumlar hazırlar | Sunum istediğinde |

## 4. Kısa cevap modu (Caveman)

Kaynak: [juliusbrussee/caveman](https://github.com/juliusbrussee/caveman)

| Skill | Komut | Ne yapar |
|---|---|---|
| `caveman` | `/caveman` ya da "be brief" | Cevapları kısaltır: dolgu yok, tüm teknik bilgi korunur. Kapatana kadar açık kalır |
| `ultracave` | `/ultracave` ya da `/caveman ultra` | En kısa mod: kelime kelime cevap. **Sadece elle açılır** |
| `megacave` | `/megacave` ya da `/caveman wenyan` | Klasik Çince ile kısaltma. **Sadece elle açılır** |
| `caveman-help` | `/caveman-help` | Caveman komutlarının listesini gösterir |
| `caveman-commit` | `/caveman-commit` ya da "commit mesajı yaz" | Kısa ve standart commit mesajı yazar |
| `caveman-review` | `/caveman-review` ya da "review the diff" | Her bulguyu tek satırda veren kod incelemesi |
| `caveman-compress` | `/caveman-compress <dosya>` | CLAUDE.md gibi not dosyalarını kısaltır, yedeğini saklar. Dosya içeriği bir modele gönderilir |
| `caveman-explore` | Kendiliğinden | Büyük kod tabanında dosya ve satır bulur |

**Caveman'i kapatmak için:** "stop caveman" ya da "normal mode" yaz.

## 5. Diğer

| Skill | Kaynak | Ne yapar | Ne zaman devreye girer |
|---|---|---|---|
| `skill-creator` | Anthropic | Yeni skill yazmana, mevcut skill'i iyileştirmene ve test etmene yardım eder | "Bir skill oluşturmak istiyorum" dediğinde |
| `writing-skills` | Superpowers | Skill yazarken iyi uygulama kuralları | Skill oluştururken ya da düzenlerken |

---

## Skill'leri açıp kapatma

Her skill'in üç durumu olabilir:

| Durum | Claude kendisi kullanır mı? | `/ad` ile çağrılabilir mi? |
|---|---|---|
| **Açık** (varsayılan) | Evet | Evet |
| **Sadece elle** | Hayır | Evet |
| **Kapalı** | Hayır | Hayır |

### Yöntem 1: Sohbette söylemek (geçici, sadece o oturum)

En kolay yol. Oturumun başında Claude'a yazman yeterli:

> "Bu oturumda caveman ve test-driven-development skill'lerini kullanma."

Oturum kapanınca etkisi biter. Kesin bir kilit değildir, Claude'a verilen bir talimattır.

### Yöntem 2: "Sadece elle" yapmak (kalıcı)

Skill'in `SKILL.md` dosyasının en üstündeki ayar bloğuna şu satırı ekle:

```yaml
---
name: brainstorming
description: ...
disable-model-invocation: true
---
```

Bundan sonra Claude bu skill'i kendiliğinden açmaz, sadece `/brainstorming` yazınca çalışır. `ultracave` ve `megacave` zaten bu şekilde ayarlı.

### Yöntem 3: Tamamen kapatmak (kalıcı)

**a) Ayar dosyasıyla (önerilen, geri alması kolay):** Repoda `.claude/settings.json` dosyası oluştur (ya da varsa düzenle):

```json
{
  "permissions": {
    "deny": [
      "Skill(caveman)",
      "Skill(investigate-first)"
    ]
  }
}
```

Listeye eklediğin skill'ler ne otomatik ne de elle çalışır. Tekrar açmak için satırı silmen yeterli.

**b) Klasörü silmek:** `.claude/skills/<skill-adı>/` klasörünü sil. Skill tamamen gider. Geri istersen GitHub geçmişinden ya da kaynak repodan tekrar eklenebilir.

### Claude'a yaptırmak

Bu değişiklikleri kendin yapmak zorunda değilsin. Bu repoyla açtığın bir oturumda şöyle yazman yeterli:

> "caveman ve investigate-first skill'lerini kapat"
> "brainstorming'i sadece elle çalışacak şekilde ayarla"

Claude ilgili dosyayı düzenleyip GitHub'a gönderir. Değişiklik bir sonraki oturumda geçerli olur.

### claude.ai sohbet ve Cowork'te

Bu repodaki skill'ler sohbette ve Cowork'te kendiliğinden görünmez. Oralarda kullanmak için skill'i claude.ai ayarlarındaki skill bölümünden zip olarak yüklemen gerekir. Yüklenen her skill'in yanında bir aç/kapa düğmesi bulunur.
