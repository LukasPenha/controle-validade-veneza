# APIs pesquisadas — 09/09/2026

| Serviço | Gratuidade e busca | Avaliação |
| --- | --- | --- |
| Open Food Facts | Gratuita, código e nome, sem chave. Atualmente 15 consultas de produto/minuto/IP e 10 buscas/minuto/IP. | Integrada. Adequada a alimentos embalados; base colaborativa sem cobertura completa garantida. |
| UPCitemdb | Gratuito sem cadastro: 100 consultas combinadas/dia, incluindo no máximo 20 buscas; limites adicionais por intervalo. | Alternativa para testar cobertura mais ampla, com franquia pequena para vários funcionários. Não integrada. |
| Go-UPC | Teste temporário, seguido de planos pagos. | Não atende à gratuidade contínua. Não integrada. |

Fontes: [Open Food Facts](https://openfoodfacts.github.io/openfoodfacts-server/api/), [UPCitemdb](https://www.upcitemdb.com/wp/docs/main/development/plan/) e [Go-UPC](https://go-upc.com/plans).

## Implementação

Open Food Facts somente leitura: API v3 para código, busca textual em `cgi/search.pl`, User-Agent, timeout e cota compartilhada. Consulta ao clicar Pesquisar ou após leitura da câmera. Resultados são texto seguro; a seleção assinada expira em 30 minutos e é vinculada ao usuário.

O cache técnico reduz chamadas. Cada lote guarda a identificação e o link da fonte. Não há catálogo editável. Dados internos de loja, usuário, quantidade e validade não são enviados à base externa; o provedor recebe termo/código e metadados normais da requisição.

## Limites

Padaria própria, hortifrúti, itens sem código e mercadorias não alimentícias podem não aparecer. Sem resultado, o sistema informa a ausência e não cria uma identidade manual. Confira nome/marca antes de registrar. A API não determina a validade de cada embalagem.

Limites por IP podem ser compartilhados com outras aplicações da hospedagem. Cache não garante disponibilidade.

## Origem e licença

Mantenha a atribuição e o link da licença. A ODbL contém obrigações de atribuição e compartilhamento aplicáveis a determinados usos/redistribuições. Consulte os [termos](https://world.openfoodfacts.org/terms-of-use) antes de redistribuir uma base derivada; tabelas separadas não eliminam automaticamente essas obrigações. Imagens têm condições próprias e não são utilizadas.

A documentação solicita User-Agent com contato e formulário de uso preenchido pelo responsável. Configure `PRODUCT_API_USER_AGENT` e consulte o formulário na documentação oficial. Nenhum cadastro externo foi realizado em seu nome.
