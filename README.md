# Sales & Invoice Prompt Extractor

## Descripción

Este módulo extrae datos de **pedidos de venta** e **invoices** de Odoo y los exporta a Google Sheets en un formato específico para ser utilizado como prompt para IA. **Funcionalidad**: Soporte multi-empresa que permite enrutar automáticamente los pedidos e invoices a diferentes hojas de Google Sheets según la empresa.

## Características

- ✅ **Soporte Multi-Empresa**: Enruta automáticamente pedidos e invoices a hojas diferentes según la empresa
- ✅ **Mapeo Configurable**: Define qué empresa va a qué hoja desde la configuración
- ✅ **Sincronización Inteligente**: Actualiza registros existentes o agrega nuevos
- ✅ **Formato Estructurado**: 22 columnas para pedidos, 23 columnas para invoices
- ✅ **Integración Google Sheets**: Conexión directa con Google Sheets API
- ✅ **Soporte EDI Mexicano**: UUID y CFDI para invoices

## Configuración

### 1. Instalación de Dependencias

```bash
pip install gspread google-auth-oauthlib
```

### 2. Configuración en Odoo

Ve a **Configuración > General > Google Sheets Extractor** y configura:

#### Campos Requeridos:
- **Google Sheet URL**: URL completa de tu hoja de Google Sheets
- **Google Service Account JSON Key**: Contenido del archivo JSON de credenciales de Google

#### Configuración de Mapeo por Empresa:
- **Company to Sheet Mapping (Orders)**: JSON que mapea nombres de empresa a nombres de hoja para pedidos
- **Company to Sheet Mapping (Invoices)**: JSON que mapea nombres de empresa a nombres de hoja para invoices

#### Ejemplo de Configuración:

```json
// Para Pedidos
{
    "GLOBAL HIRT SUMINISTROS Y SERVICIOS DE LA INDUSTRIA": "PED G",
    "FORMAS CERAMICAS": "PED F"
}

// Para Invoices
{
    "GLOBAL HIRT SUMINISTROS Y SERVICIOS DE LA INDUSTRIA": "FACT G",
    "FORMAS CERAMICAS": "FACT F"
}
```

### 3. Configuración de Google Sheets

1. **Crear Service Account** en Google Cloud Console
2. **Compartir la hoja** con el email del service account
3. **Crear las hojas** "PED G", "PED F", "FACT G", "FACT F" en tu Google Sheet
4. **Configurar permisos** de escritura para el service account

## Uso

### Extracción de Datos de Pedidos

1. Ve a **Ventas > Pedidos de Venta**
2. Selecciona uno o más pedidos
3. Haz clic en **Acción > Extraer Datos para Prompt**
4. Los datos se exportarán automáticamente a la hoja correspondiente según la empresa

### Extracción de Datos de Invoices

1. Ve a **Contabilidad > Facturas**
2. Selecciona una o más facturas de cliente
3. Haz clic en **Acción > Extraer Datos de Factura para Prompt**
4. Los datos se exportarán automáticamente a la hoja correspondiente según la empresa

### Lógica de Enrutamiento

- **Pedidos de Global**: Se exportan a la hoja "PED G"
- **Pedidos de Formas**: Se exportan a la hoja "PED F"
- **Invoices de Global**: Se exportan a la hoja "FACT G"
- **Invoices de Formas**: Se exportan a la hoja "FACT F"
- **Empresas no mapeadas**: Se exportan a la hoja por defecto

## Estructura de Datos Exportados

### Pedidos (22 columnas):

| Columna | Descripción | Ejemplo |
|---------|-------------|---------|
| 1 | Factura | F001-001 |
| 2 | Mes | 12 |
| 3 | Fecha | 2024-12-15 |
| 4 | Pedido Interno | SO001 |
| 5 | OC Cliente | OC-2024-001 |
| 6 | Domicilio | DOMICILIO |
| 7 | Cliente | Cliente ABC |
| 8 | Código Producto | PROD-001 |
| 9 | Concepto | Tabla de Cono |
| 10 | Cantidad | 5 |
| 11 | Unidad | PZA |
| 12 | Precio Unitario | 100.00 |
| 13 | Subtotal | 500.00 |
| 14 | Impuestos | 80.00 |
| 15 | Total | 580.00 |
| 16 | Moneda | Peso Mexicano |
| 17 | Tipo Cambio | 1.000000 |
| 18 | Total MXN | 580.00 |
| 19 | Días Crédito | 30 |
| 20 | Tipo Crédito | CRÉDITO |
| 21 | Categoría | FABRICACION |
| 22 | Familia | REFRACTARIOS |
| 23 | Estado | PENDIENTE |

### Invoices (23 columnas):

| Columna | Descripción | Ejemplo |
|---------|-------------|---------|
| 1 | MES | 1 |
| 2 | RFC | PRM820318FF1 |
| 3 | FACTURA | F884 |
| 4 | CLIENTE | PRODUCCION RHI MEXICO |
| 5 | TIPO | FABRICACION |
| 6 | FECHA EMISION | 03/01/2025 |
| 7 | VENCIMIENTO | 03/01/2025 |
| 8 | DIAS DE CREDITO | 90 |
| 9 | CRED-CONT | CRÉDITO |
| 10 | CÓDIGO PROD/SERV | TAB16 |
| 11 | PRODUCTO/CONCEPTO | TABLA LD2300 1/2X24X36 |
| 12 | CANTIDAD | 20 |
| 13 | UNIDAD | PIEZA |
| 14 | P.U. | $24.00 |
| 15 | IMPORTE | $480.00 |
| 16 | IVA | $76.80 |
| 17 | TOTAL | $556.80 |
| 18 | MONEDA | Dólar Americano |
| 19 | TOTAL FACTURA | $556.80 |
| 20 | TC | $18.00 |
| 21 | TOTAL MXN | $11,520.19 |
| 22 | FAMILIA | TABLA |
| 23 | CATEGORIA | FABRICACION |
| 24 | UUID | 8D6B8771-829F-4D25-8C5C-408DC1C3F229 |

## Logs y Monitoreo

El módulo registra todas las operaciones en los logs de Odoo:

- Conexión a Google Sheets
- Detección de empresa y hoja
- Operaciones de inserción/actualización
- Errores y advertencias

## Solución de Problemas

### Error: "Field must have type 'boolean', 'integer', 'float', 'char', 'selection', 'many2one' or 'datetime'"
- **Resuelto**: El campo de mapeo de empresas ahora usa tipo `Char` en lugar de `Text`
- **Solución**: Actualizar el módulo a la versión más reciente

### Datos no se exportan a la hoja correcta
- Verifica el mapeo de empresas en la configuración
- Asegúrate de que los nombres de empresa coincidan exactamente
- Revisa los logs para ver qué hoja se está usando para cada empresa
- Verifica que el JSON esté correctamente formateado

### Error: "Google Service Account Key is not set"
- Verifica que hayas pegado el contenido completo del archivo JSON en la configuración

### Error: "Worksheet not found"
- Asegúrate de que las hojas "PED G", "PED F", "FACT G", "FACT F" existan en tu Google Sheet
- Verifica que el service account tenga permisos de escritura

### Error: "Spreadsheet not found"
- Verifica que la URL de Google Sheets sea correcta
- Asegúrate de que el service account tenga acceso a la hoja

## Compatibilidad

- **Odoo**: 17.0+
- **Python**: 3.8+
- **Dependencias**: gspread, google-auth-oauthlib
- **Módulos**: l10n_mx_edi (para UUID de facturas mexicanas)

## Autor

**Adriano** - [GitHub](https://www.github.com/Adrianovaldes)

## Versión

17.0.1.0.0

## Changelog

### v17.0.1.0.0
- ✅ **NUEVO**: Soporte multi-empresa con mapeo automático a hojas diferentes
- ✅ **NUEVO**: Configuración de mapeo empresa → hoja desde interfaz
- ✅ **NUEVO**: Funcionalidad de extracción de datos de invoices
- ✅ **NUEVO**: Soporte para EDI mexicano (UUID, CFDI)
- ✅ **FIXED**: Error de tipo de campo en configuración (Text → Char)
- ✅ **MEJORADO**: Logging detallado con información de empresa y hoja
- ✅ **MEJORADO**: Procesamiento optimizado agrupando por empresa
