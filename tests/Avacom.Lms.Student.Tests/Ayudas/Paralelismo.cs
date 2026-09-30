// Las pruebas comparten piezas estáticas (las preferencias, la hora del nodo, las variables de entorno): no corren en paralelo.
[assembly: CollectionBehavior(DisableTestParallelization = true)]
