# -*- coding: utf-8 -*-
{
    'name': 'Pesquisa AIIA',
    'version': '17.0.1.0.0',
    'summary': 'Recebe leads via webhook e permite ações.',
    'description': """
        Módulo para receber informações de empresas via webhook (N8N),
        armazená-las como leads e fornecer ações rápidas (WhatsApp, Email, etc.).
    """,
    'category': 'Sales/CRM',
    'author': 'Fernando Dias - v2.0.8',
    'website': '',
    'license': 'LGPL-3', 
    'depends': [
        'base',       
        'web',       
        'mail',       
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/pesquisa_aiia_search_wizard_views.xml', 
        'views/pesquisa_aiia_lead_views.xml',          
        'views/pesquisa_aiia_search_views.xml',        
        'views/res_config_settings_views.xml'
    ],
    'installable': True,
    'application': True, 
    'auto_install': False,
}