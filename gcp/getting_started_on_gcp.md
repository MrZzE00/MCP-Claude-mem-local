# 🚀 Getting Started on GCP — MCP Claude Memory

Ce guide documente la mise en place, le fonctionnement et l'intégration du plugin de **Mémoire Sémantique (MCP)** dans vos différents IDE (Antigravity, Cursor, Claude Desktop, etc.) lorsqu'il est déployé sur **Google Cloud Platform (GCP)** avec protection **IAP (Identity-Aware Proxy)**.

---

## 1. Architecture & Authentification (IAP)

En production sur GCP, le service Cloud Run est protégé de manière stricte par **Identity-Aware Proxy (IAP)**.
Toute requête non authentifiée ou dépourvue d'un token valide est rejetée.

Pour communiquer avec l'API MCP depuis votre machine locale (via votre IDE) :
1. L'IDE lance la CLI locale `gcp/cli.py` en tâche de fond via l'interface standard **Stdio**.
2. La CLI `gcp/cli.py` récupère l'audience IAP de votre projet depuis GCP Secret Manager (secret `google-secret-id`).
3. Elle génère un **OIDC Identity Token Google** (via `gcloud auth print-identity-token`) et le met en cache localement pendant 50 minutes.
4. La CLI sert de **Proxy Stdio-to-HTTP** : elle écoute les messages JSON-RPC de votre IDE sur l'entrée standard (`stdin`), y injecte le token IAP dans les en-têtes HTTP, appelle le serveur distant, puis retransmet les réponses sur la sortie standard (`stdout`).

---

## 2. Prérequis Locaux

Avant d'activer l'intégration dans votre IDE, assurez-vous d'avoir configuré le SDK Google Cloud :

1. **Installer gcloud CLI** : [Google Cloud SDK Installation Guide](https://cloud.google.com/sdk/docs/install).
2. **Authentifier votre compte actif** :
   ```bash
   gcloud auth login
   ```
3. **Définir le projet actif** :
   ```bash
   gcloud config set project prod-ia-staffing
   ```
4. **Vérifier l'accès** :
   ```bash
   gcloud auth print-identity-token
   ```

---

## 3. Configuration dans vos IDE

### 1. Antigravity IDE (Recommandé)
Vous pouvez installer automatiquement le plugin dans votre configuration Antigravity en exécutant la commande d'installation intégrée de la CLI :

```bash
/Users/sebastien.lavayssiere/Code/MCP-Claude-mem-local/gcp/cli.py install \
  --project prod-ia-staffing \
  --url https://gen-skillz.znk.io/mcp-claude-memory
```

*Cette commande se charge d'ajouter automatiquement la clé `mcp-claude-memory-prd` dans votre fichier `~/.gemini/antigravity-ide/mcp_config.json`.*

---

### 2. Cursor
Pour intégrer la mémoire sémantique dans Cursor :

1. Ouvrez Cursor et allez dans **Settings** -> **Features** -> **MCP**.
2. Cliquez sur **+ Add New MCP Server**.
3. Remplissez les champs de configuration :
   - **Name** : `mcp-claude-memory-prd`
   - **Type** : `stdio`
   - **Command** :
     ```bash
     /Users/sebastien.lavayssiere/Code/MCP-Claude-mem-local/gcp/cli.py proxy --project prod-ia-staffing --url https://gen-skillz.znk.io/mcp-claude-memory
     ```
4. Cliquez sur **Save**. Cursor lancera le proxy en arrière-plan et découvrira automatiquement tous les outils MCP !

---

### 3. Claude Desktop
Pour utiliser la mémoire sémantique dans Claude Desktop :

1. Ouvrez votre fichier de configuration `claude_desktop_config.json` :
   - **macOS** : `~/Library/Application Support/Claude/claude_desktop_config.json`
2. Ajoutez la définition de serveur dans l'attribut `mcpServers` :
   ```json
   {
     "mcpServers": {
       "mcp-claude-memory-prd": {
         "command": "/usr/bin/python3",
         "args": [
           "/Users/sebastien.lavayssiere/Code/MCP-Claude-mem-local/gcp/cli.py",
           "proxy",
           "--project", "prod-ia-staffing",
           "--url", "https://gen-skillz.znk.io/mcp-claude-memory"
         ]
       }
     }
   }
   ```
3. Redémarrez Claude Desktop pour activer la mémoire persistante !

---

## 4. Dépannage & Commandes Utiles

### Tester la génération du Token IAP
Vous pouvez valider que la CLI arrive bien à contacter Secret Manager et à imprimer le bon token d'audience en direct :
```bash
/Users/sebastien.lavayssiere/Code/MCP-Claude-mem-local/gcp/cli.py get-token --project prod-ia-staffing
```

### Consulter les logs de transactions MCP
Le proxy redirige tous ses logs fonctionnels et ses erreurs de communication vers la sortie d'erreur standard (`stderr`). 
Pour inspecter les requêtes en temps réel de votre IDE, vous pouvez démarrer le proxy à la main dans un terminal et lui coller du JSON :
```bash
/Users/sebastien.lavayssiere/Code/MCP-Claude-mem-local/gcp/cli.py proxy --project prod-ia-staffing
```
Puis collez cette ligne JSON pour tester la découverte :
```json
{"jsonrpc": "2.0", "method": "tools/list", "id": 1}
```
*Le proxy imprimera en sortie standard le JSON des outils disponibles résolu à distance via GCP IAP.*
