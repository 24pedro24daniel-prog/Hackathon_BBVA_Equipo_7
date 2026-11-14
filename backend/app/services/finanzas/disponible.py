"""B4 — "Disponible para gastar".

formula = saldo_actual + cobros_esperados − pagos_comprometidos_hasta_proximo_vencimiento
          − minimo_operativo − reserva_impuestos        (se acota en 0)

TODO(B4): calcular_disponible(db, empresa_id, fecha_corte) -> DisponibleParaGastar
Hoy el forecast mock ya trae este bloque.
"""
